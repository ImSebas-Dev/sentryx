"""
Registrar en Celery Beat las tareas agregadas a config/beat_schedule.py después
de la migración 0005, que ya está aplicada en las instalaciones existentes.
"""
from django.conf import settings
from django.db import migrations


def register(apps, schema_editor):
    from config.beat_schedule import register_periodic_tasks
    register_periodic_tasks(
        settings,
        apps.get_model("django_celery_beat", "PeriodicTask"),
        apps.get_model("django_celery_beat", "IntervalSchedule"),
        apps.get_model("django_celery_beat", "CrontabSchedule"),
        apps.get_model("django_celery_beat", "PeriodicTasks"),
    )


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0007_alert_risk_signals"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [migrations.RunPython(register, migrations.RunPython.noop)]
