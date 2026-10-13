import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="IOC",
            fields=[
                ("id",               models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("ioc_type",         models.CharField(
                    choices=[("url","URL de phishing"),("domain","Dominio malicioso"),("ip","Dirección IP"),
                                ("sender","Remitente malicioso (hash)"),("sha256","Hash SHA-256 de adjunto"),
                                ("subject","Patrón de asunto (hash)")],
                    max_length=10,
                )),
                ("value",            models.CharField(max_length=512)),
                ("threat_level",     models.CharField(
                    choices=[("low","Bajo"),("medium","Medio"),("high","Alto"),("critical","Crítico")],
                    default="medium", max_length=10,
                )),
                ("source",           models.CharField(
                    choices=[("phishtank","PhishTank"),("openphish","OpenPhish"),("misp","MISP"),
                                ("virustotal","VirusTotal"),("manual","Manual")],
                    max_length=15,
                )),
                ("mitre_technique",  models.CharField(blank=True, max_length=20)),
                ("description",      models.TextField(blank=True)),
                ("tags",             models.JSONField(blank=True, default=list)),
                ("vt_detections",    models.IntegerField(blank=True, null=True)),
                ("vt_total",         models.IntegerField(blank=True, null=True)),
                ("raw_data",         models.JSONField(blank=True, default=dict)),
                ("brand_targeted",   models.CharField(blank=True, max_length=120)),
                ("is_active",        models.BooleanField(default=True)),
                ("first_seen",       models.DateTimeField(auto_now_add=True)),
                ("last_seen",        models.DateTimeField(auto_now=True)),
                ("expires_at",       models.DateTimeField(blank=True, null=True)),
            ],
            options={"db_table": "iocs"},
        ),
        migrations.AlterUniqueTogether(
            name="ioc",
            unique_together={("ioc_type", "value")},
        ),
        migrations.AddIndex(
            model_name="ioc",
            index=models.Index(fields=["ioc_type", "is_active"], name="iocs_type_active_idx"),
        ),
        migrations.AddIndex(
            model_name="ioc",
            index=models.Index(fields=["source"], name="iocs_source_idx"),
        ),
        migrations.AddIndex(
            model_name="ioc",
            index=models.Index(fields=["threat_level"], name="iocs_threat_idx"),
        ),
        migrations.AddIndex(
            model_name="ioc",
            index=models.Index(fields=["mitre_technique"], name="iocs_mitre_idx"),
        ),
    ]
