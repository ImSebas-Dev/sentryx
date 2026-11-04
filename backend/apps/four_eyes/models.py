"""
Sentryx v2 — Control de cuatro ojos (separación de funciones).

Un correo de alto riesgo que pide dinero, credenciales o abrir algo queda
bloqueado hasta que una segunda persona autorizada lo apruebe.

Las reglas de seguridad viven en services.py: no cambies el estado de una
ApprovalRequest directamente desde otra parte.
"""
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


def default_expiry_minutes():
    return settings.FOUR_EYES_DEFAULT_EXPIRY_MINUTES


class FourEyesPolicy(models.Model):
    class Severity(models.TextChoices):
        LOW      = "LOW",      "Baja"
        MEDIUM   = "MEDIUM",   "Media"
        HIGH     = "HIGH",     "Alta"
        CRITICAL = "CRITICAL", "Crítica"

    organization = models.CharField(max_length=120, unique=True)
    enabled      = models.BooleanField(default=True)
    min_severity = models.CharField(max_length=10, choices=Severity.choices,
                                    default=Severity.HIGH)
    require_for_payment     = models.BooleanField(default=True)
    require_for_credentials = models.BooleanField(default=True)
    require_for_attachments = models.BooleanField(default=True)
    approvers = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="+",
                    help_text="Si está vacío, aprueban los administradores")
    expiry_minutes = models.PositiveIntegerField(default=default_expiry_minutes)
    require_mfa_for_approval = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "four_eyes_policies"
        verbose_name = "Política de cuatro ojos"
        verbose_name_plural = "Políticas de cuatro ojos"

    def __str__(self):
        return f"Política de {self.organization}"


class ApprovalRequest(models.Model):
    class Status(models.TextChoices):
        PENDING   = "pending",   "Pendiente"
        APPROVED  = "approved",  "Aprobada"
        REJECTED  = "rejected",  "Rechazada"
        EXPIRED   = "expired",   "Vencida"
        CANCELLED = "cancelled", "Cancelada"

    id    = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    alert = models.ForeignKey("alerts.Alert", on_delete=models.CASCADE,
                              related_name="approval_requests")
    payment_check = models.ForeignKey("payment_shield.PaymentCheck", null=True, blank=True,
                                      on_delete=models.SET_NULL, related_name="+")
    organization = models.CharField(max_length=120, db_index=True)
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                  on_delete=models.SET_NULL, related_name="approval_requests")
    reasons = models.JSONField(default=list, blank=True)
    requester_note = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "four_eyes_requests"
        ordering = ["-created_at"]
        indexes  = [models.Index(fields=["organization", "status"]),
                    models.Index(fields=["status", "expires_at"])]
        constraints = [
            models.UniqueConstraint(fields=["alert", "requester"],
                                    condition=Q(status="pending"),
                                    name="uniq_pending_request_per_alert_requester"),
        ]

    def __str__(self):
        return f"{self.status} — alerta {self.alert_id}"

    @property
    def effective_status(self) -> str:
        # Una solicitud puede haber vencido sin que la tarea periódica haya corrido
        if self.status == self.Status.PENDING and self.expires_at <= timezone.now():
            return self.Status.EXPIRED
        return self.status
