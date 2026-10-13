"""
Sentryx v2 — Endpoints de informes semanales y mensuales.

  GET /api/v1/alerts/report/options/?period=weekly
      Lista de periodos disponibles para el selector del frontend.

  GET /api/v1/alerts/report/preview/?period=weekly&offset=0
      Resumen en JSON para mostrar la vista previa antes de descargar.

  GET /api/v1/alerts/report/?period=weekly&offset=0&export=pdf
      Descarga del informe en PDF o CSV.

Importante: el parámetro se llama 'export' y no 'format' porque DRF reserva
'?format=' para su negociación de contenido y respondería 404.

Aislamiento: se reutiliza _alert_queryset(), así que cada analista solo
obtiene sus propias alertas y el admin obtiene las de todos.
"""
import logging

from django.http import HttpResponse
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers
from drf_spectacular.utils import (
    extend_schema, inline_serializer, OpenApiExample, OpenApiParameter, OpenApiResponse,
)
from drf_spectacular.types import OpenApiTypes

from apps.alerts import reports
from apps.alerts.views import _alert_queryset
from apps.audit.models import AuditLog

logger = logging.getLogger(__name__)

EXPORT_TYPES = {
    "pdf": ("application/pdf", reports.render_pdf),
    "csv": ("text/csv; charset=utf-8", reports.render_csv),
}


def _incident_queryset(user):
    """Incidentes visibles: misma regla que el listado de incidentes."""
    from apps.incidents.views import incident_queryset
    return incident_queryset(user)


def _parse_params(request):
    """
    Validar periodo y desplazamiento. Devuelve (period, offset, error_response).
    Si hay error, los dos primeros valores son None.
    """
    period = request.query_params.get("period", "weekly")
    if period not in ("weekly", "monthly"):
        return None, None, Response(
            {"error": "El parámetro 'period' debe ser 'weekly' o 'monthly'."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        offset = int(request.query_params.get("offset", 0))
    except (TypeError, ValueError):
        offset = -1

    limit = reports.MAX_WEEKLY_OFFSET if period == "weekly" else reports.MAX_MONTHLY_OFFSET
    if not 0 <= offset <= limit:
        return None, None, Response(
            {"error": f"El parámetro 'offset' debe estar entre 0 y {limit}."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return period, offset, None


def _client_ip(request):
    return (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR", ""))


PERIOD_PARAM = OpenApiParameter("period", str, enum=["weekly", "monthly"], default="weekly")
OFFSET_PARAM = OpenApiParameter("offset", int, default=0,
                                description="0 = periodo actual, 1 = anterior, etc.")


@extend_schema(tags=["reports"], parameters=[PERIOD_PARAM], responses={200: inline_serializer(
    "ReportOptions", {"period": serializers.CharField(),
                      "options": serializers.ListField(child=serializers.DictField())})})
class ReportOptionsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        period = request.query_params.get("period", "weekly")
        if period not in ("weekly", "monthly"):
            return Response({"error": "Periodo no válido."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"period": period, "options": reports.period_options(period)})


@extend_schema(tags=["reports"], parameters=[PERIOD_PARAM, OFFSET_PARAM],
               responses={200: OpenApiTypes.OBJECT})
class ReportPreviewView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        period, offset, error = _parse_params(request)
        if error:
            return error
        data = reports.build_report_data(
            request.user, _alert_queryset(request.user),
            _incident_queryset(request.user), period, offset,
        )
        return Response(reports.build_preview(data))


@extend_schema(
    tags=["reports"], summary="Descargar informe en PDF o CSV",
    parameters=[PERIOD_PARAM, OFFSET_PARAM,
                OpenApiParameter("export", str, enum=["pdf", "csv"], default="pdf")],
    responses={(200, "application/pdf"): OpenApiTypes.BINARY,
               (200, "text/csv"): OpenApiTypes.BINARY},
    description="Cada descarga queda registrada en el log de auditoría con acción EXPORT.",
)
class ReportDownloadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        period, offset, error = _parse_params(request)
        if error:
            return error

        export = request.query_params.get("export", "pdf").lower()
        if export not in EXPORT_TYPES:
            return Response(
                {"error": "El parámetro 'export' debe ser 'pdf' o 'csv'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = reports.build_report_data(
            request.user, _alert_queryset(request.user),
            _incident_queryset(request.user), period, offset,
        )

        content_type, renderer = EXPORT_TYPES[export]
        try:
            content = renderer(data)
        except ImportError:
            logger.error("[Report] ReportLab no está instalado — reconstruir la imagen del backend.")
            return Response(
                {"error": "La generación de PDF no está disponible en el servidor. "
                          "Usa el formato CSV o pide al administrador reconstruir el backend."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception as exc:
            logger.error(f"[Report] Error generando informe: {exc}", exc_info=True)
            return Response({"error": "No se pudo generar el informe."},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        filename = reports.report_filename(data, export)

        # Toda exportación de datos queda en el log de auditoría (Ley 1581/2012)
        AuditLog.log(
            action=AuditLog.Action.EXPORT, resource="reports",
            user=request.user, ip=_client_ip(request),
            detail={
                "period": period, "offset": offset, "export": export,
                "label": data["period"]["label"],
                "alerts": data["summary"]["total"],
            },
        )

        response = HttpResponse(content, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Content-Length"]      = len(content)
        response["Cache-Control"]       = "no-store"
        # Permitir que el frontend lea el nombre del archivo desde la cabecera
        response["Access-Control-Expose-Headers"] = "Content-Disposition"
        return response
