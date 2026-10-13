"""
Sentryx v2 — Tareas programadas de Celery Beat (DatabaseScheduler).

Fuente única de los horarios. La usan:
  - la migración alerts/0005_register_periodic_tasks (se aplica en cada
    `migrate`, así que una instalación nueva queda programada sin pasos extra);
  - scripts/db/setup_celery_beat.py (para re-sincronizar a mano).

Recibir los modelos como parámetros: la migración debe pasar los modelos
históricos de apps.get_model(), no importar los de django_celery_beat.
El registro es idempotente (update_or_create por nombre).
"""
import json

TIMEZONE = "America/Bogota"


def periodic_tasks(settings):
    """Definición de cada tarea. Las frecuencias de los feeds salen de settings."""
    return [
        {
            "name": "purge_old_data",
            "task": "alerts.purge_old_data",
            "queue": "default",
            "crontab": {"minute": "0", "hour": "2"},
            "description": "Purga diaria (02:00): alertas cerradas a "
                           f"{settings.DATA_RETENTION_EVENT_LOGS_DAYS} días y auditoría a "
                           f"{settings.DATA_RETENTION_INCIDENTS_DAYS} días (Ley 1581/2012).",
        },
        {
            "name": "sync_phishtank",
            "task": "threat_intel.sync_phishtank",
            "queue": "threat_intel",
            "interval_hours": settings.PHISHTANK_SYNC_INTERVAL_HOURS,
            "description": "Sincroniza URLs de phishing desde PhishTank.",
        },
        {
            "name": "sync_openphish",
            "task": "threat_intel.sync_openphish",
            "queue": "threat_intel",
            "interval_hours": settings.OPENPHISH_SYNC_INTERVAL_HOURS,
            "description": "Sincroniza URLs de phishing desde el feed de OpenPhish.",
        },
        {
            "name": "monthly_retrain",
            "task": "ml_feedback.monthly_retrain",
            "queue": "default",
            "crontab": {"minute": "0", "hour": "3", "day_of_month": "1"},
            "description": "Reentrenamiento mensual (día 1, 03:00) si hay al menos "
                           f"{settings.ML_RETRAIN_MIN_SAMPLES} correcciones pendientes.",
        },
    ]


def register_periodic_tasks(settings, PeriodicTask, IntervalSchedule,
                            CrontabSchedule, PeriodicTasks=None):
    """Crear o actualizar las tareas. Devuelve la lista de nombres registrados."""
    names = []
    for spec in periodic_tasks(settings):
        defaults = {
            "task":        spec["task"],
            "queue":       spec["queue"],
            "args":        json.dumps([]),
            "kwargs":      json.dumps({}),
            "enabled":     True,
            "description": spec["description"],
            "interval":    None,
            "crontab":     None,
        }
        if "crontab" in spec:
            cron = {"minute": "0", "hour": "*", "day_of_week": "*",
                    "day_of_month": "*", "month_of_year": "*", **spec["crontab"]}
            defaults["crontab"], _ = CrontabSchedule.objects.get_or_create(
                timezone=TIMEZONE, **cron,
            )
        else:
            defaults["interval"], _ = IntervalSchedule.objects.get_or_create(
                every=spec["interval_hours"], period="hours",
            )
        PeriodicTask.objects.update_or_create(name=spec["name"], defaults=defaults)
        names.append(spec["name"])

    # Los modelos históricos no disparan las señales de django_celery_beat:
    # marcar el cambio a mano para que un beat ya en marcha recargue el horario.
    if PeriodicTasks is not None:
        from django.utils import timezone
        PeriodicTasks.objects.update_or_create(
            ident=1, defaults={"last_update": timezone.now()},
        )
    return names
