"""Sentryx v2 — Endpoints de la respuesta guiada (/api/v1/response/)."""
from django.conf import settings
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import generics, permissions, status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import BasePermission
from rest_framework.renderers import BaseRenderer, JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditLog
from apps.response import report, services
from apps.response.models import EmergencyContact, Playbook, ResponseSession
from apps.response.serializers import (
    EmergencyContactSerializer, PlaybookSerializer, ResponseSessionSerializer,
    StartSessionSerializer, StepSerializer,
)
from apps.users.organization import org_of

TAG = "Respuesta a incidentes"


def client_ip(request):
    return (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR", ""))


class PDFRenderer(BaseRenderer):
    """Evita el 406 de DRF cuando el cliente pide Accept: application/pdf."""
    media_type = "application/pdf"
    format = "pdf"
    charset = None

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data


def session_or_404(request, pk):
    # Responde 404 también a quien no tiene acceso: no reveles que la sesión existe
    session = generics.get_object_or_404(
        ResponseSession.objects.select_related("playbook", "user", "alert", "incident"), pk=pk)
    if not services.can_access_session(request.user, session):
        raise generics.Http404
    return session


@extend_schema(tags=[TAG], summary="Listar los playbooks disponibles")
class PlaybookListView(generics.ListAPIView):
    serializer_class   = PlaybookSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class   = None
    queryset = Playbook.objects.filter(is_active=True)


class StartSessionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=[TAG], summary="Iniciar la respuesta guiada",
        description="Crea la sesión y el incidente, agrega el evento al timeline y avisa "
                    "por correo a los admins de la organización.",
        request=StartSessionSerializer, responses={201: ResponseSessionSerializer},
    )
    def post(self, request):
        ser = StartSessionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        playbook = Playbook.objects.filter(key=data["playbook_key"], is_active=True).first()
        if playbook is None:
            return Response({"error": "Ese playbook no existe."},
                            status=status.HTTP_400_BAD_REQUEST)
        alert = None
        if data.get("alert_id"):
            alert = services.alert_for_user(request.user, data["alert_id"])
            if alert is None:
                return Response({"error": "No encontramos esa alerta."},
                                status=status.HTTP_404_NOT_FOUND)
        session = services.start_session(request.user, playbook, alert, data["answers"],
                                         client_ip(request))
        return Response(ResponseSessionSerializer(session).data, status=status.HTTP_201_CREATED)


class SessionDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=[TAG], summary="Consultar una sesión",
                   responses={200: ResponseSessionSerializer})
    def get(self, request, pk):
        return Response(ResponseSessionSerializer(session_or_404(request, pk)).data)


class StepView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=[TAG], summary="Marcar un paso y agregarlo al timeline",
                   request=StepSerializer, responses={200: ResponseSessionSerializer})
    def post(self, request, pk, step_id):
        session = session_or_404(request, pk)
        if step_id not in session.playbook.step_ids():
            return Response({"error": "Ese paso no existe."}, status=status.HTTP_404_NOT_FOUND)
        if session.status != ResponseSession.Status.IN_PROGRESS:
            return Response({"error": "Esta respuesta ya terminó."},
                            status=status.HTTP_409_CONFLICT)
        ser = StepSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        session = services.mark_step(session, step_id, ser.validated_data["done"],
                                     ser.validated_data["note"], request.user, client_ip(request))
        return Response(ResponseSessionSerializer(session).data)


class CompleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=[TAG], summary="Terminar la respuesta guiada", request=None,
                   responses={200: ResponseSessionSerializer})
    def post(self, request, pk):
        session = session_or_404(request, pk)
        if session.status == ResponseSession.Status.IN_PROGRESS:
            session = services.complete_session(session, request.user, client_ip(request))
        return Response(ResponseSessionSerializer(session).data)


class ReportView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    renderer_classes = [JSONRenderer, PDFRenderer]

    @extend_schema(tags=[TAG], summary="Descargar el paquete de denuncia en PDF",
                   responses={(200, "application/pdf"): OpenApiTypes.BINARY,
                              404: OpenApiResponse(description="La sesión no existe.")})
    def get(self, request, pk):
        session = session_or_404(request, pk)
        pdf = report.render_pdf(session)
        AuditLog.log(action=AuditLog.Action.EXPORT, resource="response.report",
                     resource_id=str(session.pk), user=request.user, ip=client_ip(request),
                     detail={"export": "pdf"})
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="paquete-denuncia-{str(session.pk)[:8]}.pdf"')
        return response


class ContactPermission(BasePermission):
    """Todos leen para poder llamar en la emergencia; solo el admin edita."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return request.method in ("GET", "HEAD", "OPTIONS") or user.is_admin


@extend_schema_view(
    list=extend_schema(tags=[TAG], summary="Listar contactos de emergencia"),
    retrieve=extend_schema(tags=[TAG], summary="Detalle de un contacto"),
    create=extend_schema(tags=[TAG], summary="Crear un contacto (solo admin)"),
    update=extend_schema(tags=[TAG], summary="Editar un contacto (solo admin)"),
    partial_update=extend_schema(tags=[TAG], summary="Editar parcialmente (solo admin)"),
    destroy=extend_schema(tags=[TAG], summary="Borrar un contacto (solo admin)"),
)
class EmergencyContactViewSet(viewsets.ModelViewSet):
    serializer_class   = EmergencyContactSerializer
    permission_classes = [ContactPermission]
    pagination_class   = None

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return EmergencyContact.objects.none()
        return services.contacts_for(org_of(self.request.user))

    def perform_create(self, serializer):
        organization = org_of(self.request.user)
        if not organization:
            raise ValidationError(
                {"error": "Tu usuario no tiene organización: pide que te la asignen."})
        contact = serializer.save(organization=organization)
        self._audit(AuditLog.Action.CREATE, contact)

    def perform_update(self, serializer):
        self._audit(AuditLog.Action.UPDATE, serializer.save())

    def perform_destroy(self, instance):
        self._audit(AuditLog.Action.DELETE, instance)
        instance.delete()

    def _audit(self, action, contact):
        AuditLog.log(action=action, resource="response.contact", resource_id=str(contact.pk),
                     user=self.request.user, ip=client_ip(self.request))


class ResponseConfigView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=[TAG], summary="Enlace del CAI Virtual y aviso de contactos",
                   responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        return Response({"cai_virtual_url": settings.CAI_VIRTUAL_URL,
                         "contact_warning": services.CONTACT_WARNING})
