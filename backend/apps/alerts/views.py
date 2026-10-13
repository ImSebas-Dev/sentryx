"""
Sentryx v2 — Views de alertas.
Aislamiento por usuario: cada analista ve solo sus propias alertas.
El admin ve todas. El reentrenamiento se dispara automáticamente
al marcar una alerta como falso positivo.
"""
import time
import logging
from django.db.models import Count
from django.utils import timezone
from datetime import timedelta
from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers
from drf_spectacular.utils import (
    extend_schema, inline_serializer, OpenApiExample, OpenApiParameter, OpenApiResponse,
)
from drf_spectacular.types import OpenApiTypes

from apps.alerts.models import Alert, PhishingCampaign
from apps.alerts.serializers import (
    AlertListSerializer, AlertDetailSerializer, AlertUpdateSerializer,
    EmailAnalysisRequestSerializer, EmailAnalysisResponseSerializer, PhishingCampaignSerializer,
)
from apps.alerts.ml_client  import analyze_email_sync, MLEngineError
from apps.alerts.service    import create_alert_from_ml_result
from apps.audit.models      import AuditLog
from apps.users.permissions import IsAnalystOrAbove, IsAuthenticatedReadOnly

logger = logging.getLogger(__name__)


def _alert_queryset(user):
    """
    Queryset base con aislamiento por usuario.
    Los admins ven todas las alertas; el resto solo las suyas.
    """
    qs = Alert.objects.select_related("campaign", "assigned_to", "owner")
    if user.is_admin:
        return qs
    return qs.filter(owner=user)


def _campaign_queryset(user):
    """
    Queryset base de campañas con aislamiento por usuario.
    """
    qs = PhishingCampaign.objects.all()
    if user.is_admin:
        return qs
    return qs.filter(owner=user)


@extend_schema(tags=["alerts"], parameters=[
    OpenApiParameter("severity", str, enum=["LOW", "MEDIUM", "HIGH", "CRITICAL"]),
    OpenApiParameter("phishing_type", str),
    OpenApiParameter("status", str),
    OpenApiParameter("domain", str, description="Dominio del remitente (contiene)"),
    OpenApiParameter("campaign", OpenApiTypes.UUID),
    OpenApiParameter("since", OpenApiTypes.DATETIME),
])
class AlertListView(generics.ListAPIView):
    serializer_class   = AlertListSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # drf-spectacular llama a get_queryset sin usuario al generar el esquema
        if getattr(self, "swagger_fake_view", False):
            return Alert.objects.none()
        qs = _alert_queryset(self.request.user)
        for field in ("severity", "phishing_type", "status"):
            val = self.request.query_params.get(field)
            if val:
                qs = qs.filter(**{field: val})
        domain = self.request.query_params.get("domain")
        if domain:
            qs = qs.filter(sender_domain__icontains=domain)
        campaign_id = self.request.query_params.get("campaign")
        if campaign_id:
            qs = qs.filter(campaign_id=campaign_id)
        since = self.request.query_params.get("since")
        if since:
            qs = qs.filter(detected_at__gte=since)
        return qs.order_by("-detected_at")


@extend_schema(tags=["alerts"])
class AlertDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticatedReadOnly]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Alert.objects.none()
        return _alert_queryset(self.request.user)

    def get_serializer_class(self):
        return AlertUpdateSerializer if self.request.method == "PATCH" \
               else AlertDetailSerializer

    def partial_update(self, request, *args, **kwargs):
        alert      = self.get_object()
        old_status = alert.status
        new_status = request.data.get("status", old_status)

        response = super().partial_update(request, *args, **kwargs)

        if new_status != old_status:
            ip = (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
                  or request.META.get("REMOTE_ADDR", ""))
            AuditLog.log(
                action=AuditLog.Action.UPDATE, resource="alerts",
                resource_id=str(alert.pk), user=request.user, ip=ip,
                detail={"old_status": old_status, "new_status": new_status},
            )
            # Reentrenamiento automático al marcar falso positivo o confirmar phishing
            if new_status == Alert.Status.FALSE_POS:
                _trigger_auto_retrain(alert, request.user, "false_positive")
            elif new_status == Alert.Status.RESOLVED and alert.risk_score >= 70:
                _trigger_auto_retrain(alert, request.user, "confirmed_phishing")

        return response


def _trigger_auto_retrain(alert, user, correction_type: str):
    """
    Registra el feedback de la corrección y dispara el reentrenamiento
    en Celery de forma asíncrona. Si ya hay un job en curso, el feedback
    queda guardado para el siguiente ciclo de reentrenamiento.
    """
    try:
        from apps.ml_feedback.models import TrainingFeedback, RetrainingJob

        if correction_type == "false_positive":
            correct_label = 0
            correct_type  = "legitimate"
            ct = TrainingFeedback.CorrectionType.FALSE_POSITIVE
        else:
            correct_label = 1
            correct_type  = alert.phishing_type
            ct = TrainingFeedback.CorrectionType.FALSE_NEGATIVE

        TrainingFeedback.objects.create(
            alert           = alert,
            correction_type = ct,
            original_label  = 1,
            original_type   = alert.phishing_type,
            original_score  = alert.risk_score,
            correct_label   = correct_label,
            correct_type    = correct_type,
            sender_domain   = alert.sender_domain,
            subject_hash    = alert.subject_hash,
            ml_features     = alert.ml_features,
            scores_by_layer = {
                "headers": alert.score_headers,
                "content": alert.score_content,
                "urls":    alert.score_urls,
            },
            reviewed_by = user,
            notes       = f"Auto-registrado al cambiar a {ct} por {user.email}",
        )

        if RetrainingJob.objects.filter(status__in=["pending", "running"]).exists():
            logger.info("[AutoRetrain] Job ya en curso — feedback guardado para el próximo ciclo.")
            return

        job  = RetrainingJob.objects.create(
            triggered_by=user, trigger=RetrainingJob.Trigger.FEEDBACK,
        )
        from apps.ml_feedback.tasks import retrain_models_task
        task = retrain_models_task.delay(str(job.id))
        job.celery_task_id = task.id
        job.save(update_fields=["celery_task_id"])

        logger.info(f"[AutoRetrain] Job={job.id} Task={task.id} Trigger={correction_type}")

    except Exception as e:
        logger.error(f"[AutoRetrain] Error: {e}", exc_info=True)


@extend_schema(
    tags=["alerts"], summary="Analizar un correo con el ensemble ML",
    request=EmailAnalysisRequestSerializer,
    responses={201: EmailAnalysisResponseSerializer, 200: EmailAnalysisResponseSerializer,
               503: OpenApiResponse(description="El motor ML no está disponible.")},
    description="201 si se creó una alerta (score ≥ 40), 200 si el correo es legítimo. "
                "Remitente, destinatario, asunto y cuerpo se guardan como SHA-256 + salt.",
    examples=[OpenApiExample("Correo BEC", request_only=True, value={
        "headers": {"from_addr": "CFO <cfo@empresa-pagos.tk>", "to_addr": "tesoreria@empresa.co",
                    "subject": "Cambio de cuenta bancaria urgente",
                    "authentication_results": "spf=fail dkim=none dmarc=fail"},
        "body_text": "Necesito que hoy actualices la cuenta del proveedor y hagas la transferencia.",
    })],
)
class EmailAnalyzeView(APIView):
    permission_classes = [IsAnalystOrAbove]

    def post(self, request):
        ser = EmailAnalysisRequestSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        data         = ser.validated_data
        headers_data = data.get("headers") or {}
        email_payload = {
            "headers": {
                "from":                   headers_data.get("from", ""),
                "subject":                headers_data.get("subject", ""),
                "reply-to":               headers_data.get("reply-to", ""),
                "authentication-results": headers_data.get("authentication-results", ""),
                "received":               headers_data.get("received", []),
            },
            "body_text": data.get("body_text", ""),
            "body_html": data.get("body_html", "") or data.get("body_text", ""),
        }

        t0 = time.perf_counter()
        try:
            ml_result = analyze_email_sync(email_payload)
        except MLEngineError as exc:
            return Response(
                {"error": str(exc), "detail": "El motor de análisis no está disponible."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        inference_ms = round((time.perf_counter() - t0) * 1000, 2)

        # El motor ML no usa el destinatario: añadirlo solo después de la
        # llamada para que se seudonimice y nunca salga del backend.
        email_payload["headers"]["to"] = headers_data.get("to", "")

        # El usuario autenticado queda registrado como owner de la alerta
        alert = create_alert_from_ml_result(
            ml_result, email_payload, "api", owner=request.user
        )

        ip = (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
              or request.META.get("REMOTE_ADDR", ""))
        AuditLog.log(
            action=AuditLog.Action.ANALYZE, resource="alerts",
            resource_id=str(alert.pk) if alert else "",
            user=request.user, ip=ip,
            detail={
                "classification": ml_result.get("classification"),
                "risk_score":     ml_result.get("risk_score"),
                "phishing_type":  ml_result.get("phishing_type"),
            },
        )

        return Response({
            "alert_id":        str(alert.pk) if alert else None,
            "risk_score":      ml_result.get("risk_score", 0),
            "classification":  ml_result.get("classification", "legitimate"),
            "phishing_type":   ml_result.get("phishing_type", "unknown"),
            "mitre_technique": ml_result.get("mitre_technique", "T1566"),
            "scores_by_layer": ml_result.get("scores_by_layer", {}),
            "url_count":       ml_result.get("url_count", 0),
            "urls_analyzed":   ml_result.get("urls_analyzed", []),
            "inference_ms":    inference_ms,
            "alert_created":   alert is not None,
        }, status=status.HTTP_201_CREATED if alert else status.HTTP_200_OK)


@extend_schema(tags=["alerts"], responses={200: inline_serializer("AlertStats", {
    "total": serializers.IntegerField(), "new": serializers.IntegerField(),
    "critical": serializers.IntegerField(),
    "by_severity": serializers.DictField(child=serializers.IntegerField()),
    "by_type": serializers.DictField(child=serializers.IntegerField()),
    "daily_last_7_days": serializers.ListField(child=serializers.DictField()),
    "false_positive_rate": serializers.FloatField(),
    "active_campaigns": serializers.IntegerField(), "week_total": serializers.IntegerField(),
})})
class AlertStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        now       = timezone.now()
        today     = now.date()
        week_ago  = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        qs = _alert_queryset(request.user)

        total    = qs.count()
        new      = qs.filter(status=Alert.Status.NEW).count()
        critical = qs.filter(severity=Alert.Severity.CRITICAL).count()

        by_severity = dict(qs.values_list("severity").annotate(c=Count("id")))
        by_type     = dict(qs.values_list("phishing_type").annotate(c=Count("id")))

        daily = []
        for i in range(7):
            day   = today - timedelta(days=i)
            count = qs.filter(detected_at__date=day).count()
            daily.append({"date": str(day), "count": count})
        daily.reverse()

        false_pos   = qs.filter(status=Alert.Status.FALSE_POS,
                                detected_at__gte=month_ago).count()
        total_month = qs.filter(detected_at__gte=month_ago).count()

        camp_qs = _campaign_queryset(request.user).filter(is_active=True)

        return Response({
            "total":               total,
            "new":                 new,
            "critical":            critical,
            "by_severity":         by_severity,
            "by_type":             by_type,
            "daily_last_7_days":   daily,
            "false_positive_rate": round(false_pos / total_month * 100, 1) if total_month else 0,
            "active_campaigns":    camp_qs.count(),
            "week_total":          qs.filter(detected_at__gte=week_ago).count(),
        })


@extend_schema(tags=["alerts"])
class CampaignListView(generics.ListAPIView):
    serializer_class   = PhishingCampaignSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return PhishingCampaign.objects.none()
        return _campaign_queryset(self.request.user).order_by("-last_seen")
