"""Sentryx v2 — Serializers de la Red de alerta."""
from rest_framework import serializers

from apps.community.constants import CONSENT_TEXT, CONSENT_VERSION, DEPARTMENTS, SECTORS
from apps.community.models import CommunitySettings
from apps.community.services import hub_ready, network_ready


class CommunitySettingsSerializer(serializers.ModelSerializer):
    consent_accepted_by_name = serializers.CharField(source="consent_accepted_by.username",
                                                     default=None, read_only=True)
    consent_text = serializers.SerializerMethodField()
    current_consent_version = serializers.SerializerMethodField()
    sector_options = serializers.SerializerMethodField()
    region_options = serializers.SerializerMethodField()
    configured = serializers.SerializerMethodField()

    class Meta:
        model  = CommunitySettings
        fields = ["organization", "enabled", "sector", "region", "consent_accepted_by_name",
                  "consent_accepted_at", "consent_version", "node_status", "last_sync_at",
                  "last_error", "deletion_pending", "consent_text", "current_consent_version",
                  "sector_options", "region_options", "configured"]
        read_only_fields = fields

    def get_consent_text(self, obj) -> str:
        return CONSENT_TEXT

    def get_current_consent_version(self, obj) -> str:
        return CONSENT_VERSION

    def get_sector_options(self, obj) -> list[dict]:
        return [{"value": value, "label": f"{value} · {label}"} for value, label in SECTORS]

    def get_region_options(self, obj) -> list[str]:
        return DEPARTMENTS

    def get_configured(self, obj) -> bool:
        return hub_ready() and network_ready()


class EnableSerializer(serializers.Serializer):
    accept_consent = serializers.BooleanField()
    sector = serializers.ChoiceField(choices=[value for value, _ in SECTORS])
    region = serializers.ChoiceField(choices=DEPARTMENTS)

    def validate_accept_consent(self, value):
        if value is not True:
            raise serializers.ValidationError("Debes aceptar el texto de consentimiento.")
        return value


class UpdateSerializer(serializers.Serializer):
    sector = serializers.ChoiceField(choices=[value for value, _ in SECTORS])
    region = serializers.ChoiceField(choices=DEPARTMENTS)


class SummarySerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    sector = serializers.CharField(required=False)
    region = serializers.CharField(required=False)
    active_campaigns = serializers.IntegerField()
    matches = serializers.IntegerField()
    last_sync_at = serializers.DateTimeField(required=False, allow_null=True)
    node_status = serializers.CharField(required=False)
