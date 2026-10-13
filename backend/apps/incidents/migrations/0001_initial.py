import django.db.models.deletion
import uuid
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
            name="Incident",
            fields=[
                ("id",               models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title",            models.CharField(max_length=255)),
                ("description",      models.TextField(blank=True)),
                ("severity",         models.CharField(
                    choices=[("LOW","Baja"),("MEDIUM","Media"),("HIGH","Alta"),("CRITICAL","Crítica")],
                    max_length=10,
                )),
                ("status",           models.CharField(
                    choices=[("new","Nuevo"),("investigating","En investigación"),("contained","Contenido"),("closed","Cerrado")],
                    default="new", max_length=15,
                )),
                ("mitre_tactic",     models.CharField(blank=True, default="Initial Access", max_length=60)),
                ("mitre_technique",  models.CharField(blank=True, max_length=20)),
                ("created_at",       models.DateTimeField(auto_now_add=True)),
                ("updated_at",       models.DateTimeField(auto_now=True)),
                ("closed_at",        models.DateTimeField(blank=True, null=True)),
                ("alerts",           models.ManyToManyField(blank=True, related_name="incidents", to="alerts.alert")),
                ("assigned_to",      models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="assigned_incidents", to=settings.AUTH_USER_MODEL,
                )),
                ("created_by",       models.ForeignKey(
                    null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="created_incidents", to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"db_table": "incidents", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="IncidentTimeline",
            fields=[
                ("id",           models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("event_type",   models.CharField(max_length=40)),
                ("description",  models.TextField()),
                ("occurred_at",  models.DateTimeField(auto_now_add=True)),
                ("incident",     models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="timeline", to="incidents.incident",
                )),
                ("actor",        models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"db_table": "incident_timeline", "ordering": ["occurred_at"]},
        ),
        migrations.AddIndex(
            model_name="incident",
            index=models.Index(fields=["status", "severity"], name="incidents_status_sev_idx"),
        ),
        migrations.AddIndex(
            model_name="incident",
            index=models.Index(fields=["created_at"], name="incidents_created_idx"),
        ),
    ]
