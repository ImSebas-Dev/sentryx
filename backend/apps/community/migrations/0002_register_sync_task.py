"""
Registrar community_sync en Celery Beat. La migración alerts/0008 no la incluye en las
instalaciones que ya la tenían aplicada cuando se agregó esta tarea.
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
        ("community", "0001_initial"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [migrations.RunPython(register, migrations.RunPython.noop)]
