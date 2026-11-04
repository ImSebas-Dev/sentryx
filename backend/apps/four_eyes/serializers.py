"""Sentryx v2 — Serializers del control de cuatro ojos."""
from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.four_eyes import services
from apps.four_eyes.models import ApprovalRequest, FourEyesPolicy
from apps.users.organization import users_of_org

User = get_user_model()


class ApprovalRequestSerializer(serializers.ModelSerializer):
    alert_id        = serializers.UUIDField(read_only=True)
    alert_severity  = serializers.CharField(source="alert.severity", read_only=True)
    alert_type      = serializers.CharField(source="alert.phishing_type", read_only=True)
    sender_domain   = serializers.CharField(source="alert.sender_domain", read_only=True)
    risk_score      = serializers.FloatField(source="alert.risk_score", read_only=True)
    requester_name  = serializers.CharField(source="requester.username", default=None, read_only=True)
    decided_by_name = serializers.CharField(source="decided_by.username", default=None, read_only=True)
    effective_status = serializers.CharField(read_only=True)
    can_decide       = serializers.SerializerMethodField()
    requires_totp    = serializers.SerializerMethodField()
    guided_response  = serializers.SerializerMethodField()

    class Meta:
        model  = ApprovalRequest
        fields = ["id", "alert_id", "alert_severity", "alert_type", "sender_domain", "risk_score",
                  "reasons", "requester_name", "requester_note", "status", "effective_status",
                  "decided_by_name", "decided_at", "decision_note", "expires_at", "created_at",
                  "can_decide", "requires_totp", "guided_response"]
        read_only_fields = fields

    def get_can_decide(self, obj) -> bool:
        user = self.context.get("user")
        if user is None or obj.requester_id == user.pk \
                or obj.effective_status != ApprovalRequest.Status.PENDING:
            return False
        policy = services.policy_for(obj.organization)
        return services.is_approver(policy, user)

    def get_requires_totp(self, obj) -> bool:
        return services.policy_for(obj.organization).require_mfa_for_approval

    def get_guided_response(self, obj) -> dict | None:
        if obj.status != ApprovalRequest.Status.REJECTED:
            return None
        return {"question": services.GUIDED_RESPONSE_QUESTION,
                "url": f"/respond?alert={obj.alert_id}"}


class ApprovalStatusSerializer(serializers.Serializer):
    """Respuesta liviana para el polling de la extensión."""
    id = serializers.UUIDField()
    status = serializers.CharField(source="effective_status")
    decided_by_name = serializers.CharField(source="decided_by.username", default=None)
    decided_at = serializers.DateTimeField()
    decision_note = serializers.CharField()
    expires_at = serializers.DateTimeField()


class CreateRequestSerializer(serializers.Serializer):
    alert_id = serializers.UUIDField()
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")


class DecisionSerializer(serializers.Serializer):
    totp_code = serializers.CharField(required=False, allow_blank=True, max_length=12, default="")
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")


class PolicySerializer(serializers.ModelSerializer):
    approver_ids = serializers.ListField(child=serializers.UUIDField(), write_only=True,
                                         required=False)
    approvers = serializers.SerializerMethodField()
    eligible_count = serializers.SerializerMethodField()
    candidates = serializers.SerializerMethodField()

    class Meta:
        model  = FourEyesPolicy
        fields = ["organization", "enabled", "min_severity", "require_for_payment",
                  "require_for_credentials", "require_for_attachments", "expiry_minutes",
                  "require_mfa_for_approval", "approver_ids", "approvers", "eligible_count",
                  "candidates", "updated_at"]
        read_only_fields = ["organization", "updated_at"]

    def get_approvers(self, obj) -> list[dict]:
        return [{"id": str(u.pk), "username": u.username} for u in obj.approvers.all()]

    def get_eligible_count(self, obj) -> int:
        return services.eligible_approvers(obj).count()

    def get_candidates(self, obj) -> list[dict]:
        # Muestra los usuarios de la empresa solo al admin que edita la política
        user = self.context.get("user")
        if user is None or not user.is_admin:
            return []
        return [{"id": str(u.pk), "username": u.username, "email": u.email,
                 "role": u.role, "mfa_enabled": u.mfa_enabled}
                for u in users_of_org(obj.organization).order_by("username")]

    def validate_expiry_minutes(self, value):
        if not 5 <= value <= 10080:
            raise serializers.ValidationError("Debe estar entre 5 minutos y 7 días.")
        return value

    def validate_approver_ids(self, value):
        valid = set(users_of_org(self.instance.organization)
                    .filter(pk__in=value).values_list("pk", flat=True))
        if set(value) != valid:
            raise serializers.ValidationError(
                "Todos los aprobadores deben ser usuarios activos de tu organización.")
        return value

    def update(self, instance, validated):
        approver_ids = validated.pop("approver_ids", None)
        instance = super().update(instance, validated)
        if approver_ids is not None:
            instance.approvers.set(approver_ids)
        return instance


class FourEyesStatsSerializer(serializers.Serializer):
    month_total = serializers.IntegerField()
    approved = serializers.IntegerField()
    rejected = serializers.IntegerField()
    expired = serializers.IntegerField()
    avg_decision_minutes = serializers.FloatField(allow_null=True)
    pending_to_approve = serializers.IntegerField()
