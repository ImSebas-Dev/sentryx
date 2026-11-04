"""Sentryx v2 — Sincronización periódica con el hub de la Red de alerta."""
from celery import shared_task


@shared_task(queue="default", name="community.sync")
def community_sync_task():
    from apps.community.services import sync
    return sync()
