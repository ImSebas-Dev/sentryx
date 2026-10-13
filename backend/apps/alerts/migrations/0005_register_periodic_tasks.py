"""
Registrar en django_celery_beat las tareas programadas de config/beat_schedule.py.
Migración de datos idempotente: se puede re-aplicar sin duplicar tareas.
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


def unregister(apps, schema_editor):
    from config.beat_schedule import periodic_tasks
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(
        name__in=[t["name"] for t in periodic_tasks(settings)]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0004_restore_owner"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [migrations.RunPython(register, unregister)]
