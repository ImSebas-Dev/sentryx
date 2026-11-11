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
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import generics, serializers
from drf_spectacular.utils import extend_schema
from drf_spectacular.types import OpenApiTypes

from apps.ml_feedback.models import TrainingFeedback, RetrainingJob
from apps.users.permissions   import IsAnalystOrAbove, IsAdminUser
from apps.audit.utils import client_ip
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
        ip = client_ip(request)
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


class FeedbackCreateSerializer(serializers.Serializer):
    """
    Corrección manual. Validar todo: estas muestras entrenan el modelo que usan
    TODAS las empresas, así que un dato basura envenena la detección de todos.
    """
    correction_type = serializers.ChoiceField(choices=TrainingFeedback.CorrectionType.choices)
    correct_label   = serializers.IntegerField(min_value=0, max_value=1)
    original_label  = serializers.IntegerField(min_value=0, max_value=1, default=1)
    original_type   = serializers.CharField(max_length=10, required=False, default="unknown")
    original_score  = serializers.FloatField(min_value=0, max_value=100, required=False, default=0)
    correct_type    = serializers.CharField(max_length=10, required=False, allow_blank=True, default="")
    sender_domain   = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    ml_features     = serializers.DictField(required=False, default=dict)
    scores_by_layer = serializers.DictField(child=serializers.FloatField(min_value=0, max_value=100),
                                            required=False, default=dict)
    notes           = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
    alert_id        = serializers.UUIDField(required=False, allow_null=True)

    def validate_ml_features(self, value):
        import json
        if len(json.dumps(value)) > 20_000:
            raise serializers.ValidationError("ml_features es demasiado grande.")
        return value


@extend_schema(tags=["ml"], request=FeedbackCreateSerializer, responses={201: OpenApiTypes.OBJECT})
class FeedbackCreateView(APIView):
    """
    POST /api/v1/ml/feedback/
    Registrar una corrección manual. Si se vincula una alerta, debe ser una
    alerta visible para el usuario (propia o, para el admin, de su empresa).
    """
    permission_classes = [IsAnalystOrAbove]

    def post(self, request):
        ser = FeedbackCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = dict(ser.validated_data)
        alert_id = data.pop("alert_id", None)

        alert = None
        if alert_id:
            from apps.alerts.views import _alert_queryset
            alert = _alert_queryset(request.user).filter(pk=alert_id).first()
            if alert is None:
                return Response({"alert_id": ["No se encontró la alerta."]},
                                status=status.HTTP_400_BAD_REQUEST)

        feedback = TrainingFeedback.objects.create(**data, alert=alert, reviewed_by=request.user)
        AuditLog.log(action=AuditLog.Action.CREATE, resource="ml_feedback",
                     resource_id=str(feedback.id), user=request.user, ip=client_ip(request),
                     detail={"correction_type": feedback.correction_type})

        return Response(
            {"id": str(feedback.id), "message": "Corrección registrada."},
            status=status.HTTP_201_CREATED,
        )
