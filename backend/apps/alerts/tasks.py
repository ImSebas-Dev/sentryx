"""
Sentryx v2 — Tareas Celery para análisis de correos y sincronización de TI.
"""
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue="alerts",
    name="alerts.analyze_email_task",
)
def analyze_email_task(self, email_payload: dict, alert_source: str = "api"):
    """
    Tarea asíncrona: envía un correo al ML Engine y crea la alerta si corresponde.
    Se encola cuando el volumen es alto o desde integraciones IMAP/webhook.

    Args:
        email_payload: dict con headers, body_text, body_html
        alert_source:  origen del correo ('api', 'imap', 'webhook')

    Returns:
        dict con alert_id (o None si legítimo) y el resultado ML
    """
    from apps.alerts.ml_client import analyze_email_sync, MLEngineError
    from apps.alerts.service   import create_alert_from_ml_result

    try:
        ml_result = analyze_email_sync(email_payload)
    except MLEngineError as exc:
        logger.warning(f"ML Engine error (intento {self.request.retries + 1}): {exc}")
        raise self.retry(exc=exc)

    alert = create_alert_from_ml_result(ml_result, email_payload, alert_source)

    alert_id = str(alert.pk) if alert else None
    if alert:
        logger.info(f"Alerta creada: {alert_id} | {alert.phishing_type} | score:{alert.risk_score:.0f}")
    else:
        logger.debug(f"Correo legítimo — score:{ml_result.get('risk_score', 0):.0f}")

    return {"alert_id": alert_id, "ml_result": ml_result}


@shared_task(
    queue="threat_intel",
    name="threat_intel.sync_phishtank",
)
def sync_phishtank_task():
    """Sincroniza URLs de phishing desde PhishTank API (free tier)."""
    import httpx
    from django.conf import settings
    from apps.threat_intel.models import IOC

    api_key  = settings.PHISHTANK_API_KEY
    if not api_key:
        logger.warning("PHISHTANK_API_KEY no configurada — saltando sync.")
        return {"synced": 0}

    try:
        url     = "https://data.phishtank.com/data/online-valid.json"
        params  = {"format": "json"}
        if api_key and api_key != "CHANGE_ME_phishtank_api_key":
            params["app_key"] = api_key

        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            entries = resp.json()

        created = 0
        for entry in entries[:500]:          # máx 500 por sincronización
            url_val = entry.get("url", "")
            if not url_val:
                continue
            _, was_created = IOC.objects.update_or_create(
                ioc_type="url", value=url_val[:512],
                defaults={
                    "source":          IOC.Source.PHISHTANK,
                    "threat_level":    IOC.ThreatLevel.HIGH,
                    "mitre_technique": "T1566.002",
                    "description":     f"PhishTank ID: {entry.get('phish_id', '')}",
                    "brand_targeted":  entry.get("target", "")[:120],
                    "is_active":       True,
                    "raw_data":        {
                        "verified":    entry.get("verified"),
                        "phish_id":    entry.get("phish_id"),
                        "submission_time": entry.get("submission_time"),
                    },
                },
            )
            if was_created:
                created += 1

        logger.info(f"PhishTank sync: {created} nuevos IOCs de {len(entries)} entradas")
        return {"synced": created, "total_entries": len(entries)}

    except Exception as exc:
        logger.error(f"Error sincronizando PhishTank: {exc}")
        return {"error": str(exc), "synced": 0}


@shared_task(
    queue="threat_intel",
    name="threat_intel.sync_openphish",
)
def sync_openphish_task():
    """Sincroniza URLs de phishing desde el feed público de OpenPhish."""
    import httpx
    from django.conf import settings
    from apps.threat_intel.models import IOC

    feed_url = settings.OPENPHISH_FEED_URL
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(feed_url)
            resp.raise_for_status()
            urls = [line.strip() for line in resp.text.splitlines() if line.strip()]

        created = 0
        for url_val in urls[:300]:
            _, was_created = IOC.objects.update_or_create(
                ioc_type="url", value=url_val[:512],
                defaults={
                    "source":          IOC.Source.OPENPHISH,
                    "threat_level":    IOC.ThreatLevel.HIGH,
                    "mitre_technique": "T1566.002",
                    "description":     "Feed OpenPhish — URL de phishing activa",
                    "is_active":       True,
                },
            )
            if was_created:
                created += 1

        logger.info(f"OpenPhish sync: {created} nuevos de {len(urls)}")
        return {"synced": created, "total_entries": len(urls)}

    except Exception as exc:
        logger.error(f"Error sincronizando OpenPhish: {exc}")
        return {"error": str(exc), "synced": 0}


@shared_task(
    queue="default",
    name="alerts.purge_old_data",
)
def purge_old_data_task():
    """
    Elimina datos vencidos según política de retención (Ley 1581/2012).
    Ejecutar diariamente con Celery Beat.
    """
    from django.conf import settings
    from apps.alerts.models import Alert
    from apps.audit.models  import AuditLog

    now             = timezone.now()
    deleted_alerts  = 0
    deleted_logs    = 0

    # Alertas resueltas/cerradas más antiguas que DATA_RETENTION_EVENT_LOGS_DAYS
    cutoff_alerts   = now - timedelta(days=settings.DATA_RETENTION_EVENT_LOGS_DAYS)
    result = Alert.objects.filter(
        status__in=["resolved", "false_pos"],
        detected_at__lt=cutoff_alerts,
    ).delete()
    deleted_alerts  = result[0]

    # Logs de auditoría más antiguos que DATA_RETENTION_INCIDENTS_DAYS
    # NOTA: AuditLog es inmutable por diseño — aquí usamos _delete directo de BD
    cutoff_logs = now - timedelta(days=settings.DATA_RETENTION_INCIDENTS_DAYS)
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM audit_log WHERE occurred_at < %s",
            [cutoff_logs]
        )
        deleted_logs = cursor.rowcount

    logger.info(f"Purga: {deleted_alerts} alertas, {deleted_logs} logs de auditoría eliminados")
    return {"deleted_alerts": deleted_alerts, "deleted_audit_logs": deleted_logs}
