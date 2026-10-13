"""
Sentryx v2 — Modelo de feedback para reentrenamiento.
Cada vez que un analista marca una alerta como falso positivo
o corrige el tipo de phishing, se guarda una muestra aquí.
Estas muestras se usan para reentrenar los modelos ML.
"""
import uuid
from django.db import models
from django.conf import settings


class TrainingFeedback(models.Model):
    """
    Muestra de correo con etiqueta corregida por un analista.
    Fuente de verdad para el reentrenamiento activo.
    """

    class CorrectionType(models.TextChoices):
        FALSE_POSITIVE = "false_positive", "Falso positivo (era legítimo)"
        FALSE_NEGATIVE = "false_negative", "Falso negativo (era phishing)"
        WRONG_TYPE     = "wrong_type",     "Tipo incorrecto"

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente de entrenamiento"
        USED    = "used",    "Usado en entrenamiento"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Alerta que originó esta corrección
    alert = models.ForeignKey(
        "alerts.Alert",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="feedback",
    )

    # Tipo de corrección
    correction_type   = models.CharField(max_length=20, choices=CorrectionType.choices)

    # Etiqueta original del modelo
    original_label    = models.IntegerField(help_text="0=legítimo, 1=phishing")
    original_type     = models.CharField(max_length=10, blank=True)
    original_score    = models.FloatField(default=0.0)

    # Etiqueta correcta según el analista
    correct_label     = models.IntegerField(help_text="0=legítimo, 1=phishing")
    correct_type      = models.CharField(max_length=10, blank=True,
                            help_text="Tipo correcto si correction_type=wrong_type")

    # Datos del correo para reentrenamiento
    # Solo metadatos no personales — Ley 1581/2012
    sender_domain     = models.CharField(max_length=255, blank=True)
    subject_hash      = models.CharField(max_length=64, blank=True)
    body_text_hash    = models.CharField(max_length=64, blank=True)

    # Features ML ya extraídas — no el texto original
    ml_features       = models.JSONField(default=dict, blank=True,
                            help_text="Features de encabezados, contenido y URLs")
    scores_by_layer   = models.JSONField(default=dict, blank=True)

    # Metadatos
    status            = models.CharField(max_length=10, choices=Status.choices,
                            default=Status.PENDING)
    reviewed_by       = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="feedback_given",
    )
    notes             = models.TextField(blank=True,
                            help_text="Comentario del analista sobre la corrección")
    created_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "training_feedback"
        ordering = ["-created_at"]
        indexes  = [
            models.Index(fields=["status"]),
            models.Index(fields=["correction_type"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"[{self.correction_type}] {self.original_type}→{self.correct_type} ({self.created_at:%Y-%m-%d})"


class RetrainingJob(models.Model):
    """
    Registro de cada ejecución de reentrenamiento.
    Guarda métricas antes y después para comparar.
    """

    class Status(models.TextChoices):
        PENDING   = "pending",   "En cola"
        RUNNING   = "running",   "Ejecutando"
        COMPLETED = "completed", "Completado"
        FAILED    = "failed",    "Falló"

    class Trigger(models.TextChoices):
        MANUAL    = "manual",    "Manual"
        FEEDBACK  = "feedback",  "Por falso positivo"
        SCHEDULED = "scheduled", "Programado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    status          = models.CharField(max_length=10, choices=Status.choices,
                          default=Status.PENDING)

    # Métricas del modelo ANTES del reentrenamiento
    metrics_before  = models.JSONField(default=dict, blank=True)

    # Métricas del modelo DESPUÉS del reentrenamiento
    metrics_after   = models.JSONField(default=dict, blank=True)

    # Cuántas muestras nuevas se usaron
    samples_used    = models.IntegerField(default=0)
    samples_total   = models.IntegerField(default=0,
                          help_text="Total de muestras (nuevas + dataset base)")

    # Origen del job. Los jobs "scheduled" los crea Celery Beat y no tienen
    # triggered_by: no asumir que ese campo viene lleno al mostrar el historial.
    trigger         = models.CharField(max_length=10, choices=Trigger.choices,
                          default=Trigger.MANUAL)

    # Quién lo disparó y cuándo
    triggered_by    = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="retraining_jobs",
    )
    triggered_at    = models.DateTimeField(auto_now_add=True)
    completed_at    = models.DateTimeField(null=True, blank=True)

    # Log de errores si falló
    error_log       = models.TextField(blank=True)

    # Task ID de Celery para seguimiento
    celery_task_id  = models.CharField(max_length=50, blank=True)

    class Meta:
        db_table = "retraining_jobs"
        ordering = ["-triggered_at"]

    def __str__(self):
        return f"Job {self.id} [{self.status}] — {self.triggered_at:%Y-%m-%d %H:%M}"

    @property
    def improvement(self):
        """Mejora en F1 entre antes y después del reentrenamiento."""
        f1_before = self.metrics_before.get("f1", 0)
        f1_after  = self.metrics_after.get("f1",  0)
        if f1_before and f1_after:
            return round(f1_after - f1_before, 4)
        return None
