"""
Sentryx v2 — Threat Intelligence especializada en phishing por correo.
IOCs sincronizados desde PhishTank, OpenPhish, MISP y VirusTotal.
"""
import uuid
from django.db import models


class IOC(models.Model):
    class IOCType(models.TextChoices):
        URL           = "url",    "URL de phishing"
        DOMAIN        = "domain", "Dominio malicioso"
        IP            = "ip",     "Dirección IP"
        EMAIL_SENDER  = "sender", "Remitente malicioso (hash)"
        HASH_SHA256   = "sha256", "Hash SHA-256 de adjunto"
        EMAIL_SUBJECT = "subject","Patrón de asunto (hash)"

    class Source(models.TextChoices):
        PHISHTANK  = "phishtank",  "PhishTank"
        OPENPHISH  = "openphish",  "OpenPhish"
        MISP       = "misp",       "MISP"
        VIRUSTOTAL = "virustotal", "VirusTotal"
        MANUAL     = "manual",     "Manual"

    class ThreatLevel(models.TextChoices):
        LOW      = "low",      "Bajo"
        MEDIUM   = "medium",   "Medio"
        HIGH     = "high",     "Alto"
        CRITICAL = "critical", "Crítico"

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ioc_type     = models.CharField(max_length=10, choices=IOCType.choices)
    value        = models.CharField(max_length=512)
    threat_level = models.CharField(max_length=10, choices=ThreatLevel.choices, default=ThreatLevel.MEDIUM)
    source       = models.CharField(max_length=15, choices=Source.choices)

    # MITRE ATT&CK (sub-técnicas de T1566)
    mitre_technique = models.CharField(max_length=20, blank=True,
                          help_text="T1566.001 | T1566.002 | T1566.003 | T1566.004")

    # Metadatos de enriquecimiento
    description    = models.TextField(blank=True)
    tags           = models.JSONField(default=list, blank=True)
    vt_detections  = models.IntegerField(null=True, blank=True)
    vt_total       = models.IntegerField(null=True, blank=True)
    raw_data       = models.JSONField(default=dict, blank=True)

    # Phishing específico — brand suplantada
    brand_targeted = models.CharField(max_length=120, blank=True,
                         help_text="Ej: Bancolombia, PayPal, Amazon")

    is_active  = models.BooleanField(default=True)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen  = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table        = "iocs"
        unique_together = [["ioc_type", "value"]]
        indexes = [
            models.Index(fields=["ioc_type", "is_active"]),
            models.Index(fields=["source"]),
            models.Index(fields=["threat_level"]),
            models.Index(fields=["mitre_technique"]),
        ]

    def __str__(self):
        return f"[{self.ioc_type}] {self.value[:60]}"
