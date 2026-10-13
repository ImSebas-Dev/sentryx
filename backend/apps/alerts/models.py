"""
Sentryx v2 — Modelo de Alerta.
Detecta phishing por correo mediante un ensemble de tres modelos ML.
Cada alerta pertenece al usuario que la generó (owner) para aislamiento
por usuario. El admin puede ver todas las alertas.
"""
import uuid
from django.db import models
from django.conf import settings


class PhishingCampaign(models.Model):
    """
    Agrupa correos de la misma campaña de phishing.
    Se detecta por correlación automática (mismo dominio en la última hora).
    """
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name        = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    indicator   = models.CharField(max_length=512, blank=True,
                    help_text="Dominio, IP o patrón que agrupa los correos")
    mitre_technique = models.CharField(max_length=20, blank=True)
    alert_count = models.PositiveIntegerField(default=0)
    is_active   = models.BooleanField(default=True)
    first_seen  = models.DateTimeField(auto_now_add=True)
    last_seen   = models.DateTimeField(auto_now=True)
    owner       = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_campaigns",
    )

    class Meta:
        db_table = "phishing_campaigns"
        ordering = ["-last_seen"]

    def __str__(self):
        return f"Campaña: {self.name} ({self.alert_count} correos)"


class Alert(models.Model):
    """
    Alerta de phishing generada por el motor ML.
    Todos los datos personales del correo se almacenan seudonimizados
    con SHA-256 + salt para cumplir la Ley 1581/2012 de Colombia.
    """

    class Severity(models.TextChoices):
        LOW      = "LOW",      "Baja"
        MEDIUM   = "MEDIUM",   "Media"
        HIGH     = "HIGH",     "Alta"
        CRITICAL = "CRITICAL", "Crítica"

    class PhishingType(models.TextChoices):
        SPEAR    = "spear",    "Spear phishing"
        WHALING  = "whaling",  "Whaling"
        BEC      = "bec",      "BEC (Business Email Compromise)"
        CLONE    = "clone",    "Clone phishing"
        VISHING  = "vishing",  "Vishing por correo"
        SMISHING = "smishing", "Smishing por correo"
        GENERIC  = "generic",  "Phishing genérico/spam"
        UNKNOWN  = "unknown",  "Sin clasificar"

    class Status(models.TextChoices):
        NEW          = "new",          "Nueva"
        ACKNOWLEDGED = "acknowledged", "Reconocida"
        RESOLVED     = "resolved",     "Resuelta"
        FALSE_POS    = "false_pos",    "Falso positivo"

    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    severity      = models.CharField(max_length=10, choices=Severity.choices, default=Severity.MEDIUM)
    phishing_type = models.CharField(max_length=10, choices=PhishingType.choices, default=PhishingType.UNKNOWN)
    status        = models.CharField(max_length=15, choices=Status.choices, default=Status.NEW)
    title         = models.CharField(max_length=255)
    description   = models.TextField(blank=True)

    risk_score    = models.FloatField(default=0.0, help_text="Score final del ensemble 0-100")
    score_headers = models.FloatField(default=0.0)
    score_content = models.FloatField(default=0.0)
    score_urls    = models.FloatField(default=0.0)

    # Datos seudonimizados — nunca almacenar en texto plano (Ley 1581/2012)
    sender_hash     = models.CharField(max_length=64, blank=True)
    recipient_hash  = models.CharField(max_length=64, blank=True)
    subject_hash    = models.CharField(max_length=64, blank=True)
    email_body_hash = models.CharField(max_length=64, blank=True)

    # Metadatos no personales — seguros de almacenar en texto plano
    sender_domain    = models.CharField(max_length=255, blank=True)
    has_attachments  = models.BooleanField(default=False)
    attachment_count = models.PositiveSmallIntegerField(default=0)
    url_count        = models.PositiveSmallIntegerField(default=0)

    ml_features     = models.JSONField(default=dict, blank=True)
    suspicious_urls = models.JSONField(default=list, blank=True)

    mitre_tactic    = models.CharField(max_length=60, blank=True, default="Initial Access")
    mitre_technique = models.CharField(max_length=20, blank=True)

    campaign = models.ForeignKey(
        PhishingCampaign,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="alerts",
    )
    # Usuario que generó la alerta — base del aislamiento por usuario
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_alerts",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_alerts",
    )

    detected_at = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "alerts"
        ordering = ["-detected_at"]
        indexes  = [
            models.Index(fields=["severity", "status"]),
            models.Index(fields=["phishing_type"]),
            models.Index(fields=["detected_at"]),
            models.Index(fields=["sender_domain"]),
            models.Index(fields=["mitre_technique"]),
            models.Index(fields=["campaign"]),
            models.Index(fields=["owner"]),
        ]

    def __str__(self):
        return f"[{self.severity}][{self.phishing_type}] {self.title} — score:{self.risk_score:.0f}"

    @property
    def classification(self):
        t = settings.ML_THRESHOLDS
        if self.risk_score >= t["critical"]:   return "critical"
        if self.risk_score >= t["phishing"]:   return "phishing"
        if self.risk_score >= t["suspicious"]: return "suspicious"
        return "legitimate"
