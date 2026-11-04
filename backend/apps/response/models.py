"""
Sentryx v2 — Respuesta guiada: "Hice clic, ¿y ahora qué?".

Guía los primeros 15 minutos después de caer en un phishing, crea el incidente y
genera el paquete de denuncia. Los playbooks se cargan por migración de datos.
"""
import uuid

from django.conf import settings
from django.db import models


class Playbook(models.Model):
    key         = models.SlugField(max_length=40, unique=True)
    title       = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    severity    = models.CharField(max_length=10, default="HIGH")
    steps       = models.JSONField(default=list,
                      help_text="Lista ordenada de {id, title, detail, critical}")
    is_active   = models.BooleanField(default=True)

    class Meta:
        db_table = "response_playbooks"
        ordering = ["key"]

    def __str__(self):
        return self.title

    def step_ids(self) -> set[str]:
        return {step["id"] for step in self.steps}


class EmergencyContact(models.Model):
    class Kind(models.TextChoices):
        BANK      = "bank",      "Banco"
        AUTHORITY = "authority", "Autoridad"
        INTERNAL  = "internal",  "Interno"

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.CharField(max_length=120, db_index=True)
    name  = models.CharField(max_length=120)
    phone = models.CharField(max_length=30, blank=True)
    url   = models.URLField(blank=True)
    kind  = models.CharField(max_length=10, choices=Kind.choices, default=Kind.BANK)

    class Meta:
        db_table = "response_emergency_contacts"
        ordering = ["kind", "name"]

    def __str__(self):
        return f"{self.name} ({self.organization})"


class ResponseSession(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "En curso"
        COMPLETED   = "completed",   "Completada"
        ABANDONED   = "abandoned",   "Abandonada"

    id   = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
                             related_name="response_sessions")
    organization = models.CharField(max_length=120, blank=True, db_index=True)
    alert = models.ForeignKey("alerts.Alert", null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="response_sessions")
    playbook = models.ForeignKey(Playbook, on_delete=models.PROTECT, related_name="sessions")
    incident = models.ForeignKey("incidents.Incident", null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name="response_sessions")
    answers     = models.JSONField(default=dict, blank=True)
    steps_state = models.JSONField(default=dict, blank=True,
                      help_text="{step_id: {done, done_at, note}}")
    started_at   = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.IN_PROGRESS)

    class Meta:
        db_table = "response_sessions"
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.playbook.key} — {self.status}"
