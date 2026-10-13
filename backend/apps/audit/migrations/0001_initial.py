import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("id",                models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("action",            models.CharField(
                    choices=[("LOGIN","Inicio de sesión"),("LOGOUT","Cierre de sesión"),("LOGIN_FAILED","Intento fallido"),
                                ("READ","Consulta"),("CREATE","Creación"),("UPDATE","Modificación"),("DELETE","Eliminación"),
                                ("EXPORT","Exportación"),("ANALYZE","Análisis de correo"),("CONFIG_CHANGE","Cambio de configuración")],
                    max_length=20,
                )),
                ("resource",          models.CharField(max_length=80)),
                ("resource_id",       models.CharField(blank=True, max_length=40)),
                ("username_snapshot", models.CharField(max_length=150)),
                ("ip_hash",           models.CharField(blank=True, max_length=64)),
                ("detail",            models.JSONField(blank=True, default=dict)),
                ("occurred_at",       models.DateTimeField(auto_now_add=True, editable=False)),
                ("user",              models.ForeignKey(
                    null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="audit_logs", to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"db_table": "audit_log", "ordering": ["-occurred_at"]},
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["user", "occurred_at"], name="audit_user_time_idx"),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["resource", "resource_id"], name="audit_resource_idx"),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["occurred_at"], name="audit_time_idx"),
        ),
    ]
