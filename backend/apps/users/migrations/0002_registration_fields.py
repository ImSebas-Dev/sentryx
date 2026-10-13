"""
Migración incremental: añade los campos de registro por correo
sobre la migración 0001_initial existente.
"""
import apps.users.models
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        # email único obligatorio
        migrations.AlterField(
            model_name="shielduser",
            name="email",
            field=models.EmailField(unique=True, max_length=254,
                                    verbose_name="email address"),
        ),
        # Cambiar USERNAME_FIELD a email
        migrations.AlterField(
            model_name="shielduser",
            name="username",
            field=models.CharField(max_length=150, unique=True,
                                   verbose_name="username"),
        ),
        # Estado de la cuenta
        migrations.AddField(
            model_name="shielduser",
            name="is_email_verified",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="shielduser",
            name="is_approved",
            field=models.BooleanField(default=False),
        ),
        # Tokens
        migrations.AddField(
            model_name="shielduser",
            name="email_verification_token",
            field=models.CharField(max_length=80, blank=True,
                                   default=apps.users.models._token),
        ),
        migrations.AddField(
            model_name="shielduser",
            name="email_verification_sent_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="shielduser",
            name="password_reset_token",
            field=models.CharField(max_length=80, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="shielduser",
            name="password_reset_sent_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        # Términos y condiciones
        migrations.AddField(
            model_name="shielduser",
            name="accepted_terms",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="shielduser",
            name="accepted_terms_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        # Aprobar usuarios existentes (admin) automáticamente
        migrations.RunSQL(
            "UPDATE shield_users SET is_email_verified=TRUE, is_approved=TRUE "
            "WHERE role='admin' OR is_superuser=TRUE;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
