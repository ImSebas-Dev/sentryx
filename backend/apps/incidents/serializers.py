"""Sentryx v2 — Serializers de incidentes."""
from rest_framework import serializers
from apps.incidents.models import Incident, IncidentTimeline
from apps.alerts.serializers import AlertListSerializer
from apps.users.organization import same_org


def validate_assignee(context, value):
    """Solo se asigna un incidente a uno mismo o a alguien de la propia empresa."""
    request = context.get("request")
    if value is None or request is None:
        return value
    if value.pk == request.user.pk or same_org(request.user, value):
        return value
    raise serializers.ValidationError("Solo puedes asignar a usuarios de tu organización.")


class IncidentTimelineSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.username", default=None)

    class Meta:
        model  = IncidentTimeline
        fields = ["id", "event_type", "description", "actor_name", "occurred_at"]
        read_only_fields = fields


class IncidentListSerializer(serializers.ModelSerializer):
    alert_count      = serializers.SerializerMethodField()
    assigned_to_name = serializers.CharField(source="assigned_to.username", default=None)
    guided_response  = serializers.SerializerMethodField()

    class Meta:
        model  = Incident
        fields = ["id", "title", "severity", "status", "mitre_technique",
                    "alert_count", "assigned_to_name", "guided_response",
                    "created_at", "updated_at"]
        read_only_fields = fields

    def get_alert_count(self, obj) -> int:
        return obj.alerts.count()

    def get_guided_response(self, obj) -> bool:
        return bool(obj.response_sessions.all())


class IncidentDetailSerializer(serializers.ModelSerializer):
    alerts           = AlertListSerializer(many=True, read_only=True)
    timeline         = IncidentTimelineSerializer(many=True, read_only=True)
    assigned_to_name = serializers.CharField(source="assigned_to.username", default=None)
    created_by_name  = serializers.CharField(source="created_by.username",  default=None)

    class Meta:
        model  = Incident
        fields = ["id", "title", "description", "severity", "status",
                    "mitre_tactic", "mitre_technique",
                    "alerts", "timeline",
                    "assigned_to_name", "created_by_name",
                    "created_at", "updated_at", "closed_at"]
        read_only_fields = [f for f in fields if f not in ("status", "description")]


class IncidentCreateSerializer(serializers.ModelSerializer):
    alert_ids = serializers.ListField(
        child=serializers.UUIDField(), write_only=True, required=False, max_length=500
    )

    class Meta:
        model  = Incident
        fields = ["title", "description", "severity", "mitre_technique",
                    "assigned_to", "alert_ids"]
        extra_kwargs = {"description": {"max_length": 10_000}}

    def create(self, validated_data):
        alert_ids = validated_data.pop("alert_ids", [])
        request   = self.context.get("request")
        incident  = Incident.objects.create(
            **validated_data,
            created_by=request.user if request else None,
        )
        if alert_ids:
            incident.alerts.set(self._visible_alerts(alert_ids))
        return incident

    def _visible_alerts(self, alert_ids):
        from apps.alerts.views import _alert_queryset
        request = self.context.get("request")
        return _alert_queryset(request.user).filter(pk__in=alert_ids)

    def validate_assigned_to(self, value):
        return validate_assignee(self.context, value)

    def validate_alert_ids(self, value):
        # Solo se pueden agrupar alertas propias (o cualquiera, si es admin)
        found = set(self._visible_alerts(value).values_list("pk", flat=True))
        missing = [str(a) for a in value if a not in found]
        if missing:
            raise serializers.ValidationError(
                f"No se encontraron estas alertas: {', '.join(missing)}"
            )
        return value


class IncidentUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Incident
        fields = ["status", "description", "assigned_to"]
        extra_kwargs = {"description": {"max_length": 10_000}}

    def validate_assigned_to(self, value):
        return validate_assignee(self.context, value)
