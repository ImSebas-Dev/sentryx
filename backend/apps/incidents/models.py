"""Sentryx v2 — Modelo de Incidente (agrupa alertas correlacionadas)."""
import uuid
from django.db import models
from django.conf import settings


class Incident(models.Model):
    class Status(models.TextChoices):
        NEW           = "new",           "Nuevo"
        INVESTIGATING = "investigating", "En investigación"
        CONTAINED     = "contained",     "Contenido"
        CLOSED        = "closed",        "Cerrado"

    class Severity(models.TextChoices):
        LOW      = "LOW",      "Baja"
        MEDIUM   = "MEDIUM",   "Media"
        HIGH     = "HIGH",     "Alta"
        CRITICAL = "CRITICAL", "Crítica"

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title       = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    severity    = models.CharField(max_length=10, choices=Severity.choices)
    status      = models.CharField(max_length=15, choices=Status.choices, default=Status.NEW)

    alerts      = models.ManyToManyField("alerts.Alert", related_name="incidents", blank=True)

    # MITRE ATT&CK — sub-técnica principal del incidente
    mitre_tactic    = models.CharField(max_length=60, blank=True, default="Initial Access")
    mitre_technique = models.CharField(max_length=20, blank=True)

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="assigned_incidents",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True,
        on_delete=models.SET_NULL, related_name="created_incidents",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at  = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "incidents"
        ordering = ["-created_at"]
        indexes  = [
            models.Index(fields=["status", "severity"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"[{self.severity}] {self.title}"


class IncidentTimeline(models.Model):
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    incident    = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="timeline")
    event_type  = models.CharField(max_length=40)
    description = models.TextField()
    actor       = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "incident_timeline"
        ordering = ["occurred_at"]
