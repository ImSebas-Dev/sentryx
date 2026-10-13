import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PhishingCampaign",
            fields=[
                ("id",               models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name",             models.CharField(max_length=255)),
                ("description",      models.TextField(blank=True)),
                ("indicator",        models.CharField(blank=True, max_length=512)),
                ("mitre_technique",  models.CharField(blank=True, max_length=20)),
                ("alert_count",      models.PositiveIntegerField(default=0)),
                ("is_active",        models.BooleanField(default=True)),
                ("first_seen",       models.DateTimeField(auto_now_add=True)),
                ("last_seen",        models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "phishing_campaigns", "ordering": ["-last_seen"]},
        ),
        migrations.CreateModel(
            name="Alert",
            fields=[
                ("id",               models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("severity",         models.CharField(
                    choices=[("LOW","Baja"),("MEDIUM","Media"),("HIGH","Alta"),("CRITICAL","Crítica")],
                    default="MEDIUM", max_length=10,
                )),
                ("phishing_type",    models.CharField(
                    choices=[("spear","Spear phishing"),("whaling","Whaling"),("bec","BEC (Business Email Compromise)"),
                             ("clone","Clone phishing"),("vishing","Vishing por correo"),("smishing","Smishing por correo"),
                             ("generic","Phishing genérico/spam"),("unknown","Sin clasificar")],
                    default="unknown", max_length=10,
                )),
                ("status",           models.CharField(
                    choices=[("new","Nueva"),("acknowledged","Reconocida"),("resolved","Resuelta"),("false_pos","Falso positivo")],
                    default="new", max_length=15,
                )),
                ("title",            models.CharField(max_length=255)),
                ("description",      models.TextField(blank=True)),
                ("risk_score",       models.FloatField(default=0.0)),
                ("score_headers",    models.FloatField(default=0.0)),
                ("score_content",    models.FloatField(default=0.0)),
                ("score_urls",       models.FloatField(default=0.0)),
                ("sender_hash",      models.CharField(blank=True, max_length=64)),
                ("recipient_hash",   models.CharField(blank=True, max_length=64)),
                ("subject_hash",     models.CharField(blank=True, max_length=64)),
                ("email_body_hash",  models.CharField(blank=True, max_length=64)),
                ("sender_domain",    models.CharField(blank=True, max_length=255)),
                ("has_attachments",  models.BooleanField(default=False)),
                ("attachment_count", models.PositiveSmallIntegerField(default=0)),
                ("url_count",        models.PositiveSmallIntegerField(default=0)),
                ("ml_features",      models.JSONField(blank=True, default=dict)),
                ("suspicious_urls",  models.JSONField(blank=True, default=list)),
                ("mitre_tactic",     models.CharField(blank=True, default="Initial Access", max_length=60)),
                ("mitre_technique",  models.CharField(blank=True, max_length=20)),
                ("detected_at",      models.DateTimeField(auto_now_add=True)),
                ("updated_at",       models.DateTimeField(auto_now=True)),
                ("campaign",         models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="alerts", to="alerts.phishingcampaign",
                )),
                ("assigned_to",      models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="assigned_alerts", to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"db_table": "alerts", "ordering": ["-detected_at"]},
        ),
        migrations.AddIndex(
            model_name="alert",
            index=models.Index(fields=["severity", "status"], name="alerts_sev_status_idx"),
        ),
        migrations.AddIndex(
            model_name="alert",
            index=models.Index(fields=["phishing_type"], name="alerts_type_idx"),
        ),
        migrations.AddIndex(
            model_name="alert",
            index=models.Index(fields=["detected_at"], name="alerts_detected_idx"),
        ),
        migrations.AddIndex(
            model_name="alert",
            index=models.Index(fields=["sender_domain"], name="alerts_domain_idx"),
        ),
        migrations.AddIndex(
            model_name="alert",
            index=models.Index(fields=["mitre_technique"], name="alerts_mitre_idx"),
        ),
        migrations.AddIndex(
            model_name="alert",
            index=models.Index(fields=["campaign"], name="alerts_campaign_idx"),
        ),
    ]
