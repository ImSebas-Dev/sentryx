"""Sentryx v2 — Views del log de auditoría (solo lectura para admins)."""
from rest_framework import generics, serializers
from drf_spectacular.utils import extend_schema
from apps.audit.models import AuditLog
from apps.users.organization import org_of
from apps.users.permissions import IsAdminUser


class AuditLogSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="username_snapshot")

    class Meta:
        model  = AuditLog
        fields = ["id", "action", "resource", "resource_id",
                    "username", "ip_hash", "detail", "occurred_at"]
        read_only_fields = fields


@extend_schema(tags=["audit"])
class AuditLogListView(generics.ListAPIView):
    """
    GET /api/v1/audit/ — log inmutable. El admin ve solo los eventos de los
    usuarios de su empresa; el superusuario de la plataforma, todos.
    """
    serializer_class   = AuditLogSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return AuditLog.objects.none()
        user = self.request.user
        qs = AuditLog.objects.select_related("user")
        if not user.is_superuser:
            organization = org_of(user)
            qs = qs.filter(user__organization=organization) if organization else qs.filter(user=user)
        username = self.request.query_params.get("user")
        if username:
            qs = qs.filter(username_snapshot=username[:150])
        action = self.request.query_params.get("action")
        if action in AuditLog.Action.values:
            qs = qs.filter(action=action)
        return qs.order_by("-occurred_at")
