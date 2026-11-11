"""Sentryx v2 — Serializers de alertas y análisis de correo."""
import os

from django.conf import settings
from rest_framework import serializers
from apps.alerts.models import Alert, PhishingCampaign
from apps.users.organization import same_org

# Límites del correo a analizar: un correo real cabe de sobra y evita que una
# sola petición agote memoria o CPU del backend y del motor ML.
MAX_HEADER_CHARS = 2_000
MAX_BODY_CHARS   = 1_000_000
MAX_RECEIVED     = 50


def validate_attachments(files) -> str:
    """
    Devuelve un mensaje de error si algún adjunto no se acepta, o "" si todos
    valen. Solo se aceptan los tipos que el sistema sabe leer (factura .xml o
    .zip) y hasta PAYMENT_SHIELD_MAX_ATTACHMENT_MB cada uno.
    """
    if len(files) > settings.ANALYZE_MAX_ATTACHMENTS:
        return f"Envía como máximo {settings.ANALYZE_MAX_ATTACHMENTS} adjuntos."
    max_bytes = settings.PAYMENT_SHIELD_MAX_ATTACHMENT_MB * 1024 * 1024
    allowed = settings.ANALYZE_ALLOWED_ATTACHMENT_EXTENSIONS
    for upload in files:
        name = os.path.basename(getattr(upload, "name", "") or "")
        if not name.lower().endswith(allowed):
            return f"Tipo de archivo no permitido ({name[:80]}). Solo {', '.join(allowed)}."
        if upload.size > max_bytes:
            return (f"El archivo {name[:80]} supera el límite de "
                    f"{settings.PAYMENT_SHIELD_MAX_ATTACHMENT_MB} MB.")
    return ""


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
            "ml_features", "suspicious_urls", "risk_signals",
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

    def validate_assigned_to(self, value):
        # Solo se asigna a alguien de la propia empresa (o a uno mismo)
        request = self.context.get("request")
        if value is None or request is None:
            return value
        if value.pk == request.user.pk or same_org(request.user, value):
            return value
        raise serializers.ValidationError("Solo puedes asignar a usuarios de tu organización.")


# ── Serializer de análisis de correo ─────────────────────
class EmailHeadersInputSerializer(serializers.Serializer):
    """Encabezados del correo a analizar."""
    from_addr              = serializers.CharField(required=False, allow_blank=True,
                                 source="from", max_length=MAX_HEADER_CHARS)
    to_addr                = serializers.CharField(required=False, allow_blank=True,
                                 source="to", max_length=MAX_HEADER_CHARS)
    subject                = serializers.CharField(required=False, allow_blank=True,
                                 max_length=MAX_HEADER_CHARS)
    reply_to               = serializers.CharField(required=False, allow_blank=True,
                                 source="reply-to", max_length=MAX_HEADER_CHARS)
    authentication_results = serializers.CharField(required=False, allow_blank=True,
                                 source="authentication-results", max_length=MAX_HEADER_CHARS * 4)
    received               = serializers.ListField(
                                 child=serializers.CharField(max_length=MAX_HEADER_CHARS),
                                 required=False, max_length=MAX_RECEIVED)


class EmailAnalysisRequestSerializer(serializers.Serializer):
    """
    Payload para POST /api/v1/alerts/analyze/
    Acepta un correo completo para análisis, en JSON o en multipart/form-data
    (en multipart los encabezados van como headers.from_addr, headers.subject...).
    """
    headers   = EmailHeadersInputSerializer(required=False)
    body_text = serializers.CharField(required=False, allow_blank=True, default="",
                                      max_length=MAX_BODY_CHARS, trim_whitespace=False)
    body_html = serializers.CharField(required=False, allow_blank=True, default="",
                                      max_length=MAX_BODY_CHARS, trim_whitespace=False)
    attachment_names = serializers.ListField(
        child=serializers.CharField(max_length=255), required=False, max_length=50,
        help_text="Nombres de los adjuntos, sin su contenido (los envía la extensión)")

    def validate(self, data):
        if not data.get("body_text") and not data.get("body_html"):
            raise serializers.ValidationError(
                "Se requiere al menos body_text o body_html."
            )
        return data


class EmailAnalysisMultipartSerializer(EmailAnalysisRequestSerializer):
    """Solo documenta la variante multipart: el archivo se lee de request.FILES."""
    attachments = serializers.ListField(
        child=serializers.FileField(), required=False,
        help_text="Adjuntos del correo. .xml y .zip se revisan como factura electrónica")


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
    severity       = serializers.CharField(required=False,
                         help_text="Severidad final tras las capas de negocio")
    payment_shield = serializers.DictField(required=False,
                         help_text="Resultado del Escudo de pagos, si aplica")
    community = serializers.DictField(required=False,
                         help_text="Coincidencia con la Red de alerta, si aplica")
    four_eyes_required = serializers.BooleanField(required=False)
    four_eyes_reasons  = serializers.ListField(required=False,
                         help_text="Motivos por los que requiere una segunda persona")
