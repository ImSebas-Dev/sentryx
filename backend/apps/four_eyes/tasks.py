"""Sentryx v2 — Tareas programadas del control de cuatro ojos."""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(queue="default", name="four_eyes.expire_requests")
def expire_requests_task():
    from apps.four_eyes.services import expire_overdue
    expired = expire_overdue()
    if expired:
        logger.info(f"[CuatroOjos] {expired} solicitudes vencidas")
    return {"expired": expired}
