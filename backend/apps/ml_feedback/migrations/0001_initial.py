import uuid
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("alerts", "0001_initial"),
        ("users",  "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="TrainingFeedback",
            fields=[
                ("id",              models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
                ("correction_type", models.CharField(max_length=20, choices=[
                    ("false_positive","Falso positivo (era legítimo)"),
                    ("false_negative","Falso negativo (era phishing)"),
                    ("wrong_type",   "Tipo incorrecto"),
                ])),
                ("original_label",  models.IntegerField()),
                ("original_type",   models.CharField(max_length=10, blank=True)),
                ("original_score",  models.FloatField(default=0.0)),
                ("correct_label",   models.IntegerField()),
                ("correct_type",    models.CharField(max_length=10, blank=True)),
                ("sender_domain",   models.CharField(max_length=255, blank=True)),
                ("subject_hash",    models.CharField(max_length=64, blank=True)),
                ("body_text_hash",  models.CharField(max_length=64, blank=True)),
                ("ml_features",     models.JSONField(default=dict, blank=True)),
                ("scores_by_layer", models.JSONField(default=dict, blank=True)),
                ("status",          models.CharField(max_length=10, default="pending", choices=[
                    ("pending","Pendiente de entrenamiento"),
                    ("used","Usado en entrenamiento"),
                ])),
                ("notes",           models.TextField(blank=True)),
                ("created_at",      models.DateTimeField(auto_now_add=True)),
                ("alert",           models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="feedback", to="alerts.alert",
                )),
                ("reviewed_by",     models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="feedback_given", to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"db_table": "training_feedback", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="RetrainingJob",
            fields=[
                ("id",             models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)),
                ("status",         models.CharField(max_length=10, default="pending", choices=[
                    ("pending","En cola"), ("running","Ejecutando"),
                    ("completed","Completado"), ("failed","Falló"),
                ])),
                ("metrics_before", models.JSONField(default=dict, blank=True)),
                ("metrics_after",  models.JSONField(default=dict, blank=True)),
                ("samples_used",   models.IntegerField(default=0)),
                ("samples_total",  models.IntegerField(default=0)),
                ("triggered_at",   models.DateTimeField(auto_now_add=True)),
                ("completed_at",   models.DateTimeField(null=True, blank=True)),
                ("error_log",      models.TextField(blank=True)),
                ("celery_task_id", models.CharField(max_length=50, blank=True)),
                ("triggered_by",   models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="retraining_jobs", to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"db_table": "retraining_jobs", "ordering": ["-triggered_at"]},
        ),
        migrations.AddIndex(
            model_name="trainingfeedback",
            index=models.Index(fields=["status"], name="feedback_status_idx"),
        ),
        migrations.AddIndex(
            model_name="trainingfeedback",
            index=models.Index(fields=["correction_type"], name="feedback_type_idx"),
        ),
        migrations.AddIndex(
            model_name="trainingfeedback",
            index=models.Index(fields=["created_at"], name="feedback_created_idx"),
        ),
    ]
