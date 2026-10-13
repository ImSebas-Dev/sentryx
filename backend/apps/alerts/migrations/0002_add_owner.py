"""
Añade campo owner a Alert y PhishingCampaign para aislamiento por usuario.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0001_initial"),
        ("users",  "0002_registration_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="alert",
            name="owner",
            field=models.ForeignKey(
                null=True, blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="owned_alerts",
                to=settings.AUTH_USER_MODEL,
                help_text="Usuario que generó esta alerta",
            ),
        ),
        migrations.AddField(
            model_name="phishingcampaign",
            name="owner",
            field=models.ForeignKey(
                null=True, blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="owned_campaigns",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name="alert",
            index=models.Index(fields=["owner"], name="alerts_owner_idx"),
        ),
    ]
