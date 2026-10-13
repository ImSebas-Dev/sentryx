"""
Sentryx v2 — Views del módulo de reentrenamiento activo.

Endpoints:
  POST /api/v1/ml/retrain/          — Disparar reentrenamiento
  GET  /api/v1/ml/retrain/status/   — Estado del job activo
  GET  /api/v1/ml/retrain/history/  — Historial de jobs
  GET  /api/v1/ml/feedback/stats/   — Estadísticas de correcciones
  POST /api/v1/ml/feedback/         — Registrar corrección manual
"""
import logging
from django.conf import settings
from django.utils import timezone
from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import generics, serializers
from drf_spectacular.utils import (
    extend_schema, inline_serializer, OpenApiExample, OpenApiParameter, OpenApiResponse,
)
from drf_spectacular.types import OpenApiTypes

from apps.ml_feedback.models import TrainingFeedback, RetrainingJob
from apps.users.permissions   import IsAnalystOrAbove, IsAdminUser
from apps.audit.models        import AuditLog

logger = logging.getLogger(__name__)


# ── Serializers ───────────────────────────────────────────
class RetrainingJobSerializer(serializers.ModelSerializer):
    triggered_by_name = serializers.CharField(
        source="triggered_by.username", default=None
    )
    trigger_display = serializers.CharField(source="get_trigger_display", read_only=True)
    improvement = serializers.SerializerMethodField()
    duration_seconds = serializers.SerializerMethodField()

    class Meta:
        model  = RetrainingJob
        fields = [
            "id", "status", "metrics_before", "metrics_after",
            "samples_used", "samples_total", "improvement",
            "trigger", "trigger_display", "triggered_by_name", "triggered_at", "completed_at",
            "duration_seconds", "error_log",
        ]

    def get_improvement(self, obj) -> float | None:
        return obj.improvement

    def get_duration_seconds(self, obj) -> int | None:
        if obj.completed_at and obj.triggered_at:
            return round((obj.completed_at - obj.triggered_at).total_seconds())
        return None


class FeedbackStatsSerializer(serializers.Serializer):
    total_pending    = serializers.IntegerField()
    total_used       = serializers.IntegerField()
    by_type          = serializers.DictField()
    last_job         = RetrainingJobSerializer(allow_null=True)
    can_retrain      = serializers.BooleanField()
    min_samples_needed = serializers.IntegerField()


# ── Views ─────────────────────────────────────────────────
@extend_schema(tags=["ml"], request=None, responses={202: OpenApiTypes.OBJECT})
class RetrainTriggerView(APIView):
    """
    POST /api/v1/ml/retrain/
    Dispara el reentrenamiento en segundo plano via Celery.
    Solo admins pueden ejecutarlo.
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        # Verificar que no haya un job corriendo
        running = RetrainingJob.objects.filter(
            status__in=["pending", "running"]
        ).first()
        if running:
            return Response(
                {
                    "error": "Ya hay un reentrenamiento en curso.",
                    "job_id": str(running.id),
                    "status": running.status,
                },
                status=status.HTTP_409_CONFLICT,
            )

        # Verificar mínimo de muestras de feedback
        pending_count = TrainingFeedback.objects.filter(
            status=TrainingFeedback.Status.PENDING
        ).count()

        MIN_SAMPLES = settings.ML_RETRAIN_MIN_SAMPLES
        if pending_count < MIN_SAMPLES:
            return Response(
                {
                    "error": f"Se necesitan al menos {MIN_SAMPLES} correcciones "
                             f"para reentrenar. Tienes {pending_count}.",
                    "pending_feedback": pending_count,
                    "min_required":     MIN_SAMPLES,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Crear job y encolar tarea
        job = RetrainingJob.objects.create(
            triggered_by=request.user, trigger=RetrainingJob.Trigger.MANUAL,
        )

        from apps.ml_feedback.tasks import retrain_models_task
        task = retrain_models_task.delay(str(job.id))

        job.celery_task_id = task.id
        job.save(update_fields=["celery_task_id"])

        # Auditoría
        ip = (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
              or request.META.get("REMOTE_ADDR", ""))
        AuditLog.log(
            action=AuditLog.Action.CONFIG_CHANGE,
            resource="ml_retrain",
            resource_id=str(job.id),
            user=request.user,
            ip=ip,
            detail={"pending_samples": pending_count, "task_id": task.id,
                    "trigger": RetrainingJob.Trigger.MANUAL},
        )

        logger.info(
            f"[Retrain] Job {job.id} encolado por {request.user.username} "
            f"con {pending_count} muestras de feedback"
        )

        return Response(
            {
                "message":         "Reentrenamiento iniciado en segundo plano.",
                "job_id":          str(job.id),
                "pending_feedback": pending_count,
                "task_id":         task.id,
            },
            status=status.HTTP_202_ACCEPTED,
        )


@extend_schema(tags=["ml"], responses={200: RetrainingJobSerializer})
class RetrainStatusView(APIView):
    """
    GET /api/v1/ml/retrain/status/
    Estado del job más reciente (para polling desde el frontend).
    """
    permission_classes = [IsAnalystOrAbove]

    def get(self, request):
        job = RetrainingJob.objects.first()
        if not job:
            return Response({"status": "no_jobs", "message": "Sin reentrenamientos previos."})

        return Response(RetrainingJobSerializer(job).data)


@extend_schema(tags=["ml"])
class RetrainHistoryView(generics.ListAPIView):
    """
    GET /api/v1/ml/retrain/history/
    Historial completo de jobs de reentrenamiento.
    """
    permission_classes = [IsAnalystOrAbove]
    serializer_class   = RetrainingJobSerializer
    queryset           = RetrainingJob.objects.all()


@extend_schema(tags=["ml"], responses={200: FeedbackStatsSerializer})
class FeedbackStatsView(APIView):
    """
    GET /api/v1/ml/feedback/stats/
    Estadísticas de correcciones pendientes para mostrar en el dashboard.
    """
    permission_classes = [IsAnalystOrAbove]

    def get(self, request):
        from django.db.models import Count

        pending = TrainingFeedback.objects.filter(
            status=TrainingFeedback.Status.PENDING
        )
        used = TrainingFeedback.objects.filter(
            status=TrainingFeedback.Status.USED
        )

        by_type = dict(
            pending.values_list("correction_type")
                   .annotate(c=Count("id"))
        )

        last_job = RetrainingJob.objects.first()
        MIN_SAMPLES = settings.ML_RETRAIN_MIN_SAMPLES

        return Response({
            "total_pending":     pending.count(),
            "total_used":        used.count(),
            "by_type":           by_type,
            "last_job":          RetrainingJobSerializer(last_job).data if last_job else None,
            "can_retrain":       pending.count() >= MIN_SAMPLES,
            "min_samples_needed": MIN_SAMPLES,
        })


@extend_schema(tags=["ml"], request=OpenApiTypes.OBJECT, responses={201: OpenApiTypes.OBJECT})
class FeedbackCreateView(APIView):
    """
    POST /api/v1/ml/feedback/
    Registrar una corrección manual (sin pasar por una alerta existente).
    """
    permission_classes = [IsAnalystOrAbove]

    def post(self, request):
        data = request.data

        required = ["correct_label", "correction_type"]
        for field in required:
            if field not in data:
                return Response(
                    {"error": f"Campo requerido: {field}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        feedback = TrainingFeedback.objects.create(
            correction_type = data["correction_type"],
            original_label  = data.get("original_label", 1),
            original_type   = data.get("original_type", "unknown"),
            original_score  = data.get("original_score", 0),
            correct_label   = data["correct_label"],
            correct_type    = data.get("correct_type", ""),
            sender_domain   = data.get("sender_domain", ""),
            ml_features     = data.get("ml_features", {}),
            scores_by_layer = data.get("scores_by_layer", {}),
            notes           = data.get("notes", ""),
            reviewed_by     = request.user,
        )

        # Vincular alerta si se proporcionó
        alert_id = data.get("alert_id")
        if alert_id:
            try:
                from apps.alerts.models import Alert
                alert = Alert.objects.get(pk=alert_id)
                feedback.alert = alert
                feedback.save(update_fields=["alert"])
            except Exception:
                pass

        return Response(
            {"id": str(feedback.id), "message": "Corrección registrada."},
            status=status.HTTP_201_CREATED,
        )
