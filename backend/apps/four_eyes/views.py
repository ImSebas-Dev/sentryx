"""Sentryx v2 — Endpoints del control de cuatro ojos (/api/v1/four-eyes/)."""
from django.db.models import Avg, DurationField, ExpressionWrapper, F, Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.alerts.models import Alert
from apps.audit.models import AuditLog
from apps.four_eyes import services
from apps.four_eyes.models import ApprovalRequest
from apps.four_eyes.serializers import (
    ApprovalRequestSerializer, ApprovalStatusSerializer, CreateRequestSerializer,
    DecisionSerializer, FourEyesStatsSerializer, PolicySerializer,
)
from apps.users.organization import org_of

TAG = "Cuatro ojos"


def client_ip(request):
    return (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR", ""))


def error_response(exc: services.FourEyesError) -> Response:
    return Response({"error": exc.message, "code": exc.code}, status=exc.http_status)


def visible_requests(user):
    """Cada quien ve lo que pidió; aprobadores y admins ven las de su organización."""
    qs = ApprovalRequest.objects.select_related("alert", "requester", "decided_by")
    own = Q(requester=user)
    organization = org_of(user)
    if not organization:
        return qs.filter(own)
    policy = services.policy_for(organization)
    if user.is_admin or services.is_approver(policy, user):
        return qs.filter(own | Q(organization=organization))
    return qs.filter(own)


def requests_to_approve(user):
    organization = org_of(user)
    if not organization:
        return ApprovalRequest.objects.none()
    if not services.is_approver(services.policy_for(organization), user):
        return ApprovalRequest.objects.none()
    return (ApprovalRequest.objects.select_related("alert", "requester", "decided_by")
            .filter(organization=organization, status=ApprovalRequest.Status.PENDING,
                    expires_at__gt=timezone.now())
            .exclude(requester=user))


class PolicyView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _policy(self, request):
        return services.policy_for(org_of(request.user))

    @extend_schema(tags=[TAG], summary="Consultar la política de la organización",
                   responses={200: PolicySerializer,
                              400: OpenApiResponse(description="El usuario no tiene organización.")})
    def get(self, request):
        policy = self._policy(request)
        if policy is None:
            return Response({"error": "Tu usuario no tiene organización."},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(PolicySerializer(policy, context={"user": request.user}).data)

    @extend_schema(tags=[TAG], summary="Editar la política (solo admin)",
                   request=PolicySerializer, responses={200: PolicySerializer})
    def put(self, request):
        if not request.user.is_admin:
            return Response({"error": "Solo un administrador puede editar la política."},
                            status=status.HTTP_403_FORBIDDEN)
        policy = self._policy(request)
        if policy is None:
            return Response({"error": "Tu usuario no tiene organización."},
                            status=status.HTTP_400_BAD_REQUEST)
        ser = PolicySerializer(policy, data=request.data, partial=True,
                               context={"user": request.user})
        ser.is_valid(raise_exception=True)
        changed = {k: str(v) for k, v in ser.validated_data.items()}
        ser.save()
        AuditLog.log(action=AuditLog.Action.FOUR_EYES_POLICY_CHANGED, resource="four_eyes.policy",
                     resource_id=str(policy.pk), user=request.user, ip=client_ip(request),
                     detail={"changed": changed})
        return Response(PolicySerializer(policy, context={"user": request.user}).data)


class RequestListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=[TAG], summary="Listar solicitudes",
        parameters=[
            OpenApiParameter("mine", bool, description="Solo las que pedí"),
            OpenApiParameter("to_approve", bool, description="Solo las que me toca decidir"),
            OpenApiParameter("status", str, enum=[c for c, _ in ApprovalRequest.Status.choices]),
            OpenApiParameter("alert", str, description="Filtrar por alerta"),
        ],
        responses={200: ApprovalRequestSerializer(many=True)},
    )
    def get(self, request):
        params = request.query_params
        if params.get("to_approve") == "true":
            qs = requests_to_approve(request.user)
        else:
            qs = visible_requests(request.user)
        if params.get("mine") == "true":
            qs = qs.filter(requester=request.user)
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("alert"):
            try:
                qs = qs.filter(alert_id=params["alert"])
            except ValueError:
                qs = qs.none()
        qs = qs.order_by("-created_at")[:200]
        return Response(ApprovalRequestSerializer(qs, many=True,
                                                  context={"user": request.user}).data)

    @extend_schema(
        tags=[TAG], summary="Pedir la aprobación de una segunda persona",
        request=CreateRequestSerializer,
        responses={201: ApprovalRequestSerializer, 200: ApprovalRequestSerializer,
                   403: OpenApiResponse(description="Otra organización o sin permiso."),
                   409: OpenApiResponse(description="No se requiere o no hay otro aprobador.")},
    )
    def post(self, request):
        ser = CreateRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        alert = Alert.objects.select_related("owner").filter(
            pk=ser.validated_data["alert_id"]).first()
        if alert is None:
            return Response({"error": "La alerta no existe."}, status=status.HTTP_404_NOT_FOUND)
        try:
            request_obj, created = services.create_request(
                alert, request.user, ser.validated_data["note"], client_ip(request))
        except services.FourEyesError as exc:
            return error_response(exc)
        return Response(ApprovalRequestSerializer(request_obj, context={"user": request.user}).data,
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@extend_schema(tags=[TAG], summary="Detalle de una solicitud")
class RequestDetailView(generics.RetrieveAPIView):
    serializer_class   = ApprovalRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ApprovalRequest.objects.none()
        return visible_requests(self.request.user)

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "user": self.request.user}


class _DecisionView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    # Comparte el cupo de los endpoints de 2FA: frena el ensayo de códigos TOTP
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "mfa"
    approve = True

    def post(self, request, pk):
        ser = DecisionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        if not ApprovalRequest.objects.filter(pk=pk).exists():
            return Response({"error": "La solicitud no existe."}, status=status.HTTP_404_NOT_FOUND)
        try:
            request_obj = services.decide(
                pk, request.user, self.approve, ser.validated_data["totp_code"],
                ser.validated_data["note"], client_ip(request))
        except services.FourEyesError as exc:
            return error_response(exc)
        return Response(ApprovalRequestSerializer(request_obj, context={"user": request.user}).data)


class RequestApproveView(_DecisionView):
    approve = True

    @extend_schema(tags=[TAG], summary="Aprobar una solicitud",
                   request=DecisionSerializer, responses={200: ApprovalRequestSerializer})
    def post(self, request, pk):
        return super().post(request, pk)


class RequestRejectView(_DecisionView):
    approve = False

    @extend_schema(tags=[TAG], summary="Rechazar una solicitud (nota obligatoria)",
                   request=DecisionSerializer, responses={200: ApprovalRequestSerializer})
    def post(self, request, pk):
        return super().post(request, pk)


class RequestCancelView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=[TAG], summary="Cancelar mi solicitud pendiente",
                   request=None, responses={200: ApprovalRequestSerializer})
    def post(self, request, pk):
        if not ApprovalRequest.objects.filter(pk=pk).exists():
            return Response({"error": "La solicitud no existe."}, status=status.HTTP_404_NOT_FOUND)
        try:
            request_obj = services.cancel(pk, request.user, client_ip(request))
        except services.FourEyesError as exc:
            return error_response(exc)
        return Response(ApprovalRequestSerializer(request_obj, context={"user": request.user}).data)


class RequestStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "four_eyes_status"

    @extend_schema(tags=[TAG], summary="Estado liviano para el polling de la extensión",
                   responses={200: ApprovalStatusSerializer})
    def get(self, request, pk):
        request_obj = generics.get_object_or_404(visible_requests(request.user), pk=pk)
        return Response(ApprovalStatusSerializer(request_obj).data)


class FourEyesStatsView(APIView):
    """Evidencia de uso del control para el dashboard."""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=[TAG], summary="Métricas del mes y pendientes por aprobar",
                   responses={200: FourEyesStatsSerializer})
    def get(self, request):
        now = timezone.localtime()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        qs = visible_requests(request.user).filter(created_at__gte=month_start)
        decided = qs.filter(decided_at__isnull=False)
        avg = decided.annotate(
            took=ExpressionWrapper(F("decided_at") - F("created_at"),
                                   output_field=DurationField()),
        ).aggregate(value=Avg("took"))["value"]
        return Response({
            "month_total": qs.count(),
            "approved": qs.filter(status=ApprovalRequest.Status.APPROVED).count(),
            "rejected": qs.filter(status=ApprovalRequest.Status.REJECTED).count(),
            "expired": qs.filter(status=ApprovalRequest.Status.EXPIRED).count(),
            "avg_decision_minutes": round(avg.total_seconds() / 60, 1) if avg else None,
            "pending_to_approve": requests_to_approve(request.user).count(),
        })
