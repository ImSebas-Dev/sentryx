"""
Sentryx v2 — Red de alerta entre pymes (lado del nodo).

Solo se guardan aquí huellas de indicadores y datos agregados de la red. El opt-in
vive en CommunitySettings y está apagado por defecto.
"""
import uuid

from django.conf import settings
from django.db import models


class CommunitySettings(models.Model):
    class NodeStatus(models.TextChoices):
        DISABLED      = "disabled",      "Red desactivada"
        NOT_CONFIGURED = "not_configured", "Falta configuración"
        ACTIVE        = "active",        "Conectado"
        UNREACHABLE   = "unreachable",   "Hub sin respuesta"
        SUSPENDED     = "suspended",     "Nodo rechazado por el hub"

    organization = models.CharField(max_length=120, unique=True)
    enabled = models.BooleanField(default=False)
    sector  = models.CharField(max_length=1, blank=True)
    region  = models.CharField(max_length=60, blank=True)
    consent_accepted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                            on_delete=models.SET_NULL, related_name="+")
    consent_accepted_at = models.DateTimeField(null=True, blank=True)
    consent_version = models.CharField(max_length=10, blank=True)
    node_status = models.CharField(max_length=15, choices=NodeStatus.choices,
                                   default=NodeStatus.DISABLED)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=200, blank=True)
    # Quedó pendiente pedirle al hub que borre: reintenta en cada sincronización
    deletion_pending = models.BooleanField(default=False)

    class Meta:
        db_table = "community_settings"

    def __str__(self):
        return f"{self.organization}: {'activa' if self.enabled else 'apagada'}"


class CommunityIndicator(models.Model):
    """Copia local del feed. Es de la instalación, no de una empresa."""
    ioc_hash = models.CharField(max_length=64, unique=True)
    ioc_type = models.CharField(max_length=10)
    company_count = models.PositiveIntegerField(default=0)
    sectors = models.JSONField(default=list, blank=True)
    regions = models.JSONField(default=list, blank=True)
    phishing_type = models.CharField(max_length=10, blank=True)
    mitre_technique = models.CharField(max_length=20, blank=True)
    first_seen = models.DateField()
    last_seen = models.DateField(db_index=True)

    class Meta:
        db_table = "community_indicators"

    def __str__(self):
        return f"{self.ioc_type}:{self.ioc_hash[:12]} ({self.company_count})"


class OutboxEntry(models.Model):
    """
    Indicador candidato a enviarse. Se calcula al analizar porque ese es el único
    momento en que existe la URL completa: en la alerta queda truncada y sin parámetros.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.CharField(max_length=120, db_index=True)
    alert = models.ForeignKey("alerts.Alert", on_delete=models.CASCADE,
                              related_name="community_outbox")
    ioc_type = models.CharField(max_length=10)
    ioc_hash = models.CharField(max_length=64)
    sent_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "community_outbox"
        constraints = [models.UniqueConstraint(fields=["alert", "ioc_hash"],
                                               name="uniq_outbox_alert_ioc")]
