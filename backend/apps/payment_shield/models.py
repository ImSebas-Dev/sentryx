"""
Sentryx v2 — Escudo de pagos (anti-BEC).

Supplier es el directorio de proveedores de confianza de cada empresa.
PaymentCheck guarda el resultado de comparar un correo contra ese directorio.

Nunca guardes aquí el número de cuenta completo, el cuerpo ni el asunto del correo
(Ley 1581/2012): de la cuenta solo se conservan los últimos 4 dígitos y un HMAC.
"""
import uuid

from django.conf import settings
from django.db import models


class Supplier(models.Model):
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.CharField(max_length=120, db_index=True)
    name         = models.CharField(max_length=200)
    nit          = models.CharField(max_length=15, help_text="Solo dígitos, sin DV")
    dv           = models.CharField(max_length=1, help_text="Dígito de verificación")
    email_domains = models.JSONField(default=list, blank=True,
                        help_text="Dominios autorizados para enviar correo del proveedor")
    contact_phone = models.CharField(max_length=30, blank=True,
                        help_text="Número de confianza para la llamada de verificación")
    bank_name     = models.CharField(max_length=80, blank=True)
    account_last4 = models.CharField(max_length=4, blank=True)
    account_hmac  = models.CharField(max_length=64, blank=True,
                        help_text="HMAC-SHA256 del número completo con PAYMENT_SHIELD_SECRET")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payment_suppliers"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "nit"],
                                    name="uniq_supplier_org_nit"),
        ]

    def __str__(self):
        return f"{self.name} (NIT {self.nit}-{self.dv})"


class PaymentCheck(models.Model):

    class Verdict(models.TextChoices):
        MATCH                = "match",                "Coincide con el proveedor"
        ACCOUNT_MISMATCH     = "account_mismatch",     "La cuenta no coincide"
        DOMAIN_MISMATCH      = "domain_mismatch",      "El dominio no está autorizado"
        LOOKALIKE_DOMAIN     = "lookalike_domain",     "Dominio parecido al del proveedor"
        UNKNOWN_SUPPLIER     = "unknown_supplier",     "Proveedor desconocido"
        INVOICE_INCONSISTENT = "invoice_inconsistent", "Factura inconsistente"

    class Status(models.TextChoices):
        PENDING  = "pending_verification", "Pendiente de verificación"
        CALLED   = "verified_by_call",     "Verificado por llamada"
        REJECTED = "rejected",             "Rechazado"
        APPROVED = "approved",             "Aprobado"

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    alert        = models.ForeignKey("alerts.Alert", null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name="payment_checks")
    owner        = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name="+")
    organization = models.CharField(max_length=120, blank=True, db_index=True)

    intent_detected = models.BooleanField(default=False)
    matched_keywords = models.JSONField(default=list, blank=True)
    extracted_banks  = models.JSONField(default=list, blank=True)
    extracted_account_last4 = models.JSONField(default=list, blank=True)

    supplier      = models.ForeignKey(Supplier, null=True, blank=True,
                                      on_delete=models.SET_NULL, related_name="checks")
    sender_domain = models.CharField(max_length=255, blank=True)
    verdict       = models.CharField(max_length=25, choices=Verdict.choices)

    invoice_data   = models.JSONField(default=dict, blank=True)
    invoice_checks = models.JSONField(default=list, blank=True)

    status = models.CharField(max_length=25, choices=Status.choices, default=Status.PENDING)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="+")
    verified_at = models.DateTimeField(null=True, blank=True)
    verification_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payment_checks"
        ordering = ["-created_at"]
        indexes  = [models.Index(fields=["organization", "created_at"])]

    def __str__(self):
        return f"{self.verdict} — {self.sender_domain or 'sin dominio'}"

    @property
    def is_risky(self) -> bool:
        return self.intent_detected and self.verdict != self.Verdict.MATCH
