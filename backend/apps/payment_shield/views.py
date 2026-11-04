"""
Sentryx v2 — Endpoints del Escudo de pagos (/api/v1/payment-shield/).

Filtra siempre por la organización del usuario, también para los admins: el
directorio de proveedores de una empresa no se comparte con ninguna otra.
"""
from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiResponse, extend_schema, extend_schema_view, inline_serializer,
)
from rest_framework import generics, serializers, status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditLog
from apps.payment_shield.models import PaymentCheck, Supplier
from apps.payment_shield.serializers import (
    PaymentCheckSerializer, SupplierSerializer, VerifyCheckSerializer,
)
from apps.users.organization import org_of
from apps.users.permissions import IsAnalystOrAbove

TAG = "Escudo de pagos"


def client_ip(request):
    return (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR", ""))


class SupplierPermission(BasePermission):
    """Analistas leen; solo el admin crea, edita y borra."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_analyst):
            return False
        return request.method in ("GET", "HEAD", "OPTIONS") or user.is_admin


@extend_schema_view(
    list=extend_schema(tags=[TAG], summary="Listar proveedores de la organización"),
    retrieve=extend_schema(tags=[TAG], summary="Detalle de un proveedor"),
    create=extend_schema(tags=[TAG], summary="Registrar un proveedor (solo admin)"),
    update=extend_schema(tags=[TAG], summary="Editar un proveedor (solo admin)"),
    partial_update=extend_schema(tags=[TAG], summary="Editar parcialmente (solo admin)"),
    destroy=extend_schema(tags=[TAG], summary="Borrar un proveedor (solo admin)"),
)
class SupplierViewSet(viewsets.ModelViewSet):
    serializer_class   = SupplierSerializer
    permission_classes = [SupplierPermission]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Supplier.objects.none()
        organization = org_of(self.request.user)
        if not organization:
            return Supplier.objects.none()
        return Supplier.objects.filter(organization=organization)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        user = getattr(self.request, "user", None)
        context["organization"] = org_of(user) if user else ""
        return context

    def perform_create(self, serializer):
        organization = org_of(self.request.user)
        if not organization:
            raise ValidationError(
                {"error": "Tu usuario no tiene organización: pide que te la asignen."})
        supplier = serializer.save(organization=organization, created_by=self.request.user)
        self._audit(AuditLog.Action.SUPPLIER_CREATED, supplier)

    def perform_update(self, serializer):
        self._audit(AuditLog.Action.SUPPLIER_UPDATED, serializer.save())

    def perform_destroy(self, instance):
        self._audit(AuditLog.Action.SUPPLIER_DELETED, instance)
        instance.delete()

    def _audit(self, action, supplier):
        # Registra solo metadatos: el número de cuenta nunca entra a la auditoría
        AuditLog.log(action=action, resource="payment_shield.supplier",
                     resource_id=str(supplier.pk), user=self.request.user,
                     ip=client_ip(self.request), detail={"nit": supplier.nit})


def visible_checks(user):
    qs = PaymentCheck.objects.select_related("supplier", "verified_by")
    organization = org_of(user)
    # Un usuario sin organización no tiene equipo: muéstrale solo sus propios análisis
    return qs.filter(organization=organization) if organization else qs.filter(owner=user)


@extend_schema(tags=[TAG], summary="Listar verificaciones de pago")
class PaymentCheckListView(generics.ListAPIView):
    serializer_class   = PaymentCheckSerializer
    permission_classes = [IsAnalystOrAbove]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return PaymentCheck.objects.none()
        return visible_checks(self.request.user)


@extend_schema(tags=[TAG], summary="Detalle de una verificación de pago")
class PaymentCheckDetailView(generics.RetrieveAPIView):
    serializer_class   = PaymentCheckSerializer
    permission_classes = [IsAnalystOrAbove]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return PaymentCheck.objects.none()
        return visible_checks(self.request.user)


class PaymentCheckVerifyView(APIView):
    permission_classes = [IsAnalystOrAbove]

    @extend_schema(
        tags=[TAG], summary="Registrar el resultado de la verificación",
        request=VerifyCheckSerializer, responses={200: PaymentCheckSerializer},
        description="`verified_by_call` registra la llamada al número de confianza; "
                    "`rejected` y `approved` cierran la verificación.",
    )
    def post(self, request, pk):
        check = generics.get_object_or_404(visible_checks(request.user), pk=pk)
        ser = VerifyCheckSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        result = ser.validated_data["result"]

        # Una verificación cerrada no se reabre: analiza de nuevo si cambió algo
        if check.status in (PaymentCheck.Status.REJECTED, PaymentCheck.Status.APPROVED):
            return Response({"error": "Esta verificación ya está cerrada."},
                            status=status.HTTP_409_CONFLICT)

        # Importa aquí: four_eyes depende de los modelos de esta app
        from apps.four_eyes import services as four_eyes
        if result == PaymentCheck.Status.APPROVED and not four_eyes.approval_gate_open(check):
            return Response(
                {"error": "Para aprobar este pago hace falta la aprobación de una segunda persona.",
                 "code": "four_eyes_required"},
                status=status.HTTP_409_CONFLICT)

        check.status = result
        check.verified_by = request.user
        check.verified_at = timezone.now()
        check.verification_notes = ser.validated_data["notes"]
        check.save(update_fields=["status", "verified_by", "verified_at",
                                  "verification_notes"])
        AuditLog.log(action=AuditLog.Action.PAYMENT_VERIFIED, resource="payment_shield.check",
                     resource_id=str(check.pk), user=request.user, ip=client_ip(request),
                     detail={"result": result, "verdict": check.verdict})
        return Response(PaymentCheckSerializer(check).data)


class PaymentRiskAcknowledgeView(APIView):
    """Deja constancia de que el usuario leyó el aviso y decidió continuar."""
    permission_classes = [IsAnalystOrAbove]

    @extend_schema(
        tags=[TAG], summary="Registrar «Entiendo el riesgo» desde la extensión",
        request=None,
        responses={200: inline_serializer("PaymentRiskAck", {
                       "acknowledged": serializers.BooleanField()}),
                   409: OpenApiResponse(description="El correo requiere cuatro ojos.")},
    )
    def post(self, request, pk):
        check = generics.get_object_or_404(visible_checks(request.user), pk=pk)
        from apps.four_eyes import services as four_eyes
        if four_eyes.blocks_risk_acknowledgement(check):
            return Response(
                {"error": "Este correo requiere la aprobación de una segunda persona.",
                 "code": "four_eyes_required"},
                status=status.HTTP_409_CONFLICT)
        AuditLog.log(action=AuditLog.Action.PAYMENT_RISK_ACK, resource="payment_shield.check",
                     resource_id=str(check.pk), user=request.user, ip=client_ip(request),
                     detail={"verdict": check.verdict})
        return Response({"acknowledged": True})
