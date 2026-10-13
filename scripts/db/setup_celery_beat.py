"""
Sentryx v2 — Re-sincronizar las tareas programadas de Celery Beat.

Normalmente no hace falta: la migración alerts/0005_register_periodic_tasks
las registra en cada `migrate`. Usar este script solo si alguien las borró o
modificó desde /admin/django_celery_beat/ y se quiere volver a los valores
de config/beat_schedule.py:

    docker compose exec -T backend python manage.py shell < scripts/db/setup_celery_beat.py
"""
from django.conf import settings
from django_celery_beat.models import (
    PeriodicTask, PeriodicTasks, IntervalSchedule, CrontabSchedule,
)
from config.beat_schedule import register_periodic_tasks

register_periodic_tasks(settings, PeriodicTask, IntervalSchedule,
                        CrontabSchedule, PeriodicTasks)

print("Tareas programadas configuradas:")
for t in PeriodicTask.objects.order_by("name"):
    print(f"  {t.name:24} {t.task:30} {t.schedule}")
