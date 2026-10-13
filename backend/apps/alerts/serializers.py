"""Sentryx v2 — Serializers de alertas y análisis de correo."""
from rest_framework import serializers
from apps.alerts.models import Alert, PhishingCampaign


class PhishingCampaignSerializer(serializers.ModelSerializer):
    class Meta:
        model  = PhishingCampaign
        fields = ["id", "name", "description", "indicator", "mitre_technique",
                    "alert_count", "is_active", "first_seen", "last_seen"]
        read_only_fields = fields


class AlertListSerializer(serializers.ModelSerializer):
    """Vista resumida para el panel de alertas."""
    campaign_name    = serializers.CharField(source="campaign.name", default=None)
    assigned_to_name = serializers.CharField(source="assigned_to.username", default=None)

    class Meta:
        model  = Alert
        fields = [
            "id", "severity", "phishing_type", "status", "title",
            "risk_score", "score_headers", "score_content", "score_urls",
            "sender_domain", "mitre_technique", "url_count",
            "has_attachments", "campaign_name", "assigned_to_name",
            "detected_at",
        ]
        read_only_fields = fields


class AlertDetailSerializer(serializers.ModelSerializer):
    """Vista completa de una alerta — incluye features ML."""
    campaign         = PhishingCampaignSerializer(read_only=True)
    assigned_to_name = serializers.CharField(source="assigned_to.username", default=None)
    classification   = serializers.SerializerMethodField()

    class Meta:
        model  = Alert
        fields = [
            "id", "severity", "phishing_type", "status", "title", "description",
            "risk_score", "score_headers", "score_content", "score_urls",
            "sender_domain", "has_attachments", "attachment_count", "url_count",
            "ml_features", "suspicious_urls",
            "mitre_tactic", "mitre_technique",
            "campaign", "assigned_to_name",
            "detected_at", "updated_at",
            "classification",
            # Hashes — se incluyen para trazabilidad interna (no son el dato original)
            "sender_hash", "subject_hash",
        ]
        read_only_fields = [f for f in fields if f not in ("status", "assigned_to_name")]

    def get_classification(self, obj) -> str:
        return obj.classification


class AlertUpdateSerializer(serializers.ModelSerializer):
    """Solo los campos que un analista puede modificar."""
    class Meta:
        model  = Alert
        fields = ["status", "assigned_to"]


# ── Serializer de análisis de correo ─────────────────────
class EmailHeadersInputSerializer(serializers.Serializer):
    """Encabezados del correo a analizar."""
    from_addr              = serializers.CharField(required=False, allow_blank=True,
                                 source="from")
    to_addr                = serializers.CharField(required=False, allow_blank=True,
                                 source="to")
    subject                = serializers.CharField(required=False, allow_blank=True)
    reply_to               = serializers.CharField(required=False, allow_blank=True,
                                 source="reply-to")
    authentication_results = serializers.CharField(required=False, allow_blank=True,
                                 source="authentication-results")
    received               = serializers.ListField(
                                 child=serializers.CharField(), required=False)


class EmailAnalysisRequestSerializer(serializers.Serializer):
    """
    Payload para POST /api/v1/alerts/analyze/
    Acepta un correo completo para análisis.
    """
    headers   = EmailHeadersInputSerializer(required=False)
    body_text = serializers.CharField(required=False, allow_blank=True, default="")
    body_html = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, data):
        if not data.get("body_text") and not data.get("body_html"):
            raise serializers.ValidationError(
                "Se requiere al menos body_text o body_html."
            )
        return data


class EmailAnalysisResponseSerializer(serializers.Serializer):
    """Respuesta del análisis — incluye la alerta creada si es phishing."""
    alert_id       = serializers.UUIDField(allow_null=True)
    risk_score     = serializers.FloatField()
    classification = serializers.CharField()
    phishing_type  = serializers.CharField()
    mitre_technique= serializers.CharField()
    scores_by_layer= serializers.DictField()
    url_count      = serializers.IntegerField()
    urls_analyzed  = serializers.ListField()
    inference_ms   = serializers.FloatField()
    alert_created  = serializers.BooleanField()
