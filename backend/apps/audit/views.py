"""Sentryx v2 — Views del log de auditoría (solo lectura para admins)."""
from rest_framework import generics, serializers
from drf_spectacular.utils import extend_schema
from apps.audit.models import AuditLog
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
    """GET /api/v1/audit/ — log inmutable, solo administradores."""
    serializer_class   = AuditLogSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = AuditLog.objects.all()
        user = self.request.query_params.get("user")
        if user:
            qs = qs.filter(username_snapshot=user)
        action = self.request.query_params.get("action")
        if action:
            qs = qs.filter(action=action)
        return qs.order_by("-occurred_at")
