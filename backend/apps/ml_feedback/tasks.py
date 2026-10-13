"""
Sentryx v2 — Tarea Celery de reentrenamiento activo.

Flujo:
  1. Carga el dataset base (emails_dataset.csv)
  2. Añade las muestras de feedback del analista (TrainingFeedback)
  3. Reentrena los tres modelos con el dataset combinado
  4. Evalúa métricas antes y después
  5. Guarda los nuevos modelos en el volumen Docker
  6. Actualiza el RetrainingJob con el resultado

Los pasos 1–5 los ejecuta el ML Engine (POST /admin/retrain).
"""
import json
import logging

import httpx
from celery import shared_task

logger = logging.getLogger(__name__)

# Debe ser menor que soft_time_limit para que el error quede registrado en el job
RETRAIN_HTTP_TIMEOUT = 570.0


@shared_task(
    bind=True,
    name="ml_feedback.retrain_models",
    queue="default",
    max_retries=1,
    soft_time_limit=600,   # 10 minutos máximo
    time_limit=660,
)
def retrain_models_task(self, job_id: str):
    """
    Reentrenamiento activo de los modelos ML.
    Llamar vía: retrain_models_task.delay(str(job_id))
    """
    from apps.ml_feedback.models import RetrainingJob, TrainingFeedback
    from django.utils import timezone

    job = RetrainingJob.objects.get(pk=job_id)
    job.status         = RetrainingJob.Status.RUNNING
    job.celery_task_id = self.request.id
    job.save(update_fields=["status", "celery_task_id"])

    logger.info(f"[Retrain] Iniciando job {job_id}")

    try:
        # ── 1. Obtener muestras de feedback pendientes ────────
        feedback_qs = TrainingFeedback.objects.filter(
            status=TrainingFeedback.Status.PENDING
        )
        feedback_samples = list(feedback_qs.values(
            "id", "correct_label", "correct_type", "ml_features",
            "scores_by_layer", "sender_domain",
        ))
        feedback_ids = [f["id"] for f in feedback_samples]
        n_feedback = len(feedback_samples)
        logger.info(f"[Retrain] {n_feedback} muestras de feedback disponibles")

        # ── 2. Reentrenar en el ML Engine ─────────────────────
        result = _run_retraining(feedback_samples)

        # ── 3. Marcar feedback como usado ─────────────────────
        # Solo las muestras enviadas; las que llegaron durante el
        # entrenamiento quedan pendientes para el siguiente ciclo.
        TrainingFeedback.objects.filter(id__in=feedback_ids).update(
            status=TrainingFeedback.Status.USED
        )

        # ── 4. Actualizar job con resultados ──────────────────
        job.status        = RetrainingJob.Status.COMPLETED
        job.completed_at  = timezone.now()
        job.samples_used  = n_feedback
        job.samples_total = result.get("total_samples", 0)
        job.metrics_before= result.get("metrics_before", {})
        job.metrics_after = result.get("metrics_after",  {})
        job.save()

        logger.info(
            f"[Retrain] Job {job_id} completado. "
            f"F1: {result.get('metrics_before',{}).get('f1','?')} → "
            f"{result.get('metrics_after',{}).get('f1','?')}"
        )

        return {
            "status":        "completed",
            "job_id":        job_id,
            "metrics_after": result.get("metrics_after", {}),
        }

    except Exception as exc:
        logger.error(f"[Retrain] Job {job_id} falló: {exc}", exc_info=True)
        job.status    = RetrainingJob.Status.FAILED
        job.error_log = str(exc)
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "error_log", "completed_at"])
        raise


def _feedback_rows(feedback_samples: list) -> list:
    """
    Convierte el feedback en filas con las columnas del dataset de entrenamiento.
    El correo original no se guarda (seudonimización), así que se usan el
    dominio del remitente y las features extraídas por el ML Engine.
    """
    return [
        {
            "label":         s["correct_label"],
            "phishing_type": s["correct_type"] or "legitimate",
            "from":          s.get("sender_domain", ""),
            "subject":       "",
            "body":          json.dumps(s.get("ml_features", {})),
            "auth_results":  "",
            "reply_to":      "",
            "received_hops": 3,
        }
        for s in feedback_samples
    ]


def _run_retraining(feedback_samples: list) -> dict:
    """
    Pide al ML Engine que reentrene los modelos con el feedback.

    El entrenamiento corre en el contenedor ml_engine, que tiene scikit-learn,
    los pipelines, el dataset y el volumen de modelos; el ML Engine recarga
    los modelos al terminar.
    """
    from django.conf import settings

    url = f"{settings.ML_ENGINE_URL}/admin/retrain"
    try:
        resp = httpx.post(
            url,
            json={"feedback": _feedback_rows(feedback_samples)},
            headers={"X-API-Key": settings.ML_ENGINE_API_KEY},
            timeout=httpx.Timeout(RETRAIN_HTTP_TIMEOUT, connect=10.0),
        )
    except httpx.TimeoutException:
        raise RuntimeError(f"El ML Engine no terminó el reentrenamiento en {RETRAIN_HTTP_TIMEOUT:.0f} s.")
    except httpx.HTTPError as exc:
        raise RuntimeError(f"No se pudo conectar al ML Engine ({url}): {exc}")

    if resp.status_code != 200:
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        raise RuntimeError(f"ML Engine retornó {resp.status_code}: {str(detail)[-2000:]}")

    data = resp.json()
    logger.info("[Retrain] Salida del entrenamiento:\n%s", data.get("log_tail", ""))
    return data


@shared_task(name="ml_feedback.monthly_retrain", queue="default")
def monthly_retrain_task():
    """
    Reentrenamiento mensual (Celery Beat, día 1 a las 03:00 America/Bogota).

    Solo encola retrain_models_task si hay al menos ML_RETRAIN_MIN_SAMPLES
    correcciones pendientes y ningún job en estado pending o running.
    Devuelve un dict con "status" ("queued" o "skipped") para que el
    resultado quede visible en Flower y en django_celery_results.
    """
    from django.conf import settings
    from django.db import transaction
    from apps.audit.models import AuditLog
    from apps.ml_feedback.models import RetrainingJob, TrainingFeedback

    min_samples = settings.ML_RETRAIN_MIN_SAMPLES

    # Bloquear la tabla de jobs mientras se decide: evita crear un segundo job
    # si un falso positivo dispara un reentrenamiento en el mismo instante.
    with transaction.atomic():
        active = (RetrainingJob.objects.select_for_update()
                  .filter(status__in=[RetrainingJob.Status.PENDING,
                                      RetrainingJob.Status.RUNNING])
                  .first())
        if active:
            logger.info(
                "[MonthlyRetrain] Omitido: el job %s está en estado %s.",
                active.id, active.status,
            )
            return {"status": "skipped", "reason": "job_in_progress",
                    "job_id": str(active.id)}

        pending = TrainingFeedback.objects.filter(
            status=TrainingFeedback.Status.PENDING
        ).count()
        if pending < min_samples:
            logger.info(
                "[MonthlyRetrain] Omitido: %s correcciones pendientes, se necesitan %s.",
                pending, min_samples,
            )
            return {"status": "skipped", "reason": "not_enough_samples",
                    "pending_feedback": pending, "min_required": min_samples}

        job = RetrainingJob.objects.create(trigger=RetrainingJob.Trigger.SCHEDULED)

    # Encolar fuera de la transacción: el worker debe encontrar el job ya
    # guardado al empezar.
    task = retrain_models_task.delay(str(job.id))
    RetrainingJob.objects.filter(pk=job.pk).update(celery_task_id=task.id or "")

    AuditLog.log(
        action=AuditLog.Action.CONFIG_CHANGE, resource="ml_retrain",
        resource_id=str(job.id), actor="system",
        detail={"trigger": RetrainingJob.Trigger.SCHEDULED,
                "pending_samples": pending, "task_id": task.id},
    )
    logger.info("[MonthlyRetrain] Job %s encolado con %s correcciones.", job.id, pending)
    return {"status": "queued", "job_id": str(job.id), "pending_feedback": pending}
