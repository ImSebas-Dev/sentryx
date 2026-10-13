"""
Pruebas del reentrenamiento mensual (ml_feedback.monthly_retrain).
retrain_models_task se reemplaza por un mock: con CELERY_TASK_ALWAYS_EAGER
llamaría de verdad al ML Engine.
"""
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings

from apps.audit.models import AuditLog
from apps.ml_feedback.models import RetrainingJob, TrainingFeedback
from apps.ml_feedback.tasks import monthly_retrain_task
from tests.utils import make_user

DELAY = "apps.ml_feedback.tasks.retrain_models_task.delay"


def _feedback(n):
    for _ in range(n):
        TrainingFeedback.objects.create(
            correction_type=TrainingFeedback.CorrectionType.FALSE_POSITIVE,
            original_label=1, correct_label=0,
        )


@override_settings(ML_RETRAIN_MIN_SAMPLES=5)
class TestMonthlyRetrain(TestCase):

    @patch(DELAY)
    def test_skips_without_enough_samples(self, mock_delay):
        _feedback(4)
        result = monthly_retrain_task()

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "not_enough_samples")
        self.assertEqual(result["pending_feedback"], 4)
        mock_delay.assert_not_called()
        self.assertFalse(RetrainingJob.objects.exists())

    @patch(DELAY)
    def test_skips_with_job_in_progress(self, mock_delay):
        _feedback(10)
        running = RetrainingJob.objects.create(status=RetrainingJob.Status.RUNNING)

        result = monthly_retrain_task()

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "job_in_progress")
        self.assertEqual(result["job_id"], str(running.id))
        mock_delay.assert_not_called()
        self.assertEqual(RetrainingJob.objects.count(), 1)

    @patch(DELAY)
    def test_queues_scheduled_job(self, mock_delay):
        mock_delay.return_value = MagicMock(id="celery-task-123")
        _feedback(5)
        # Un job anterior ya terminado no debe bloquear el disparo
        RetrainingJob.objects.create(status=RetrainingJob.Status.COMPLETED)

        result = monthly_retrain_task()

        self.assertEqual(result["status"], "queued")
        job = RetrainingJob.objects.get(pk=result["job_id"])
        self.assertEqual(job.trigger, RetrainingJob.Trigger.SCHEDULED)
        self.assertIsNone(job.triggered_by)
        self.assertEqual(job.celery_task_id, "celery-task-123")
        mock_delay.assert_called_once_with(str(job.id))

        log = AuditLog.objects.get(resource="ml_retrain", resource_id=str(job.id))
        self.assertEqual(log.action, AuditLog.Action.CONFIG_CHANGE)
        self.assertEqual(log.username_snapshot, "system")
        self.assertEqual(log.detail["trigger"], "scheduled")
        self.assertEqual(log.detail["pending_samples"], 5)


class TestRetrainTriggerLabels(TestCase):
    """El historial expone el origen de cada job para la página de reentrenamiento."""

    def test_history_includes_trigger(self):
        from rest_framework.test import APIClient
        admin = make_user("admin@sentryx.local", role="admin")
        RetrainingJob.objects.create(trigger=RetrainingJob.Trigger.SCHEDULED,
                                     status=RetrainingJob.Status.COMPLETED)
        RetrainingJob.objects.create(trigger=RetrainingJob.Trigger.FEEDBACK,
                                     triggered_by=admin,
                                     status=RetrainingJob.Status.COMPLETED)
        client = APIClient()
        client.force_authenticate(admin)
        resp = client.get("/api/v1/ml/retrain/history/")
        self.assertEqual(resp.status_code, 200)
        rows = resp.data["results"]
        self.assertEqual({r["trigger"] for r in rows}, {"scheduled", "feedback"})
        displays = {r["trigger"]: r["trigger_display"] for r in rows}
        self.assertEqual(displays["scheduled"], "Programado")
        self.assertEqual(displays["feedback"], "Por falso positivo")

    @patch("apps.ml_feedback.tasks.retrain_models_task.delay")
    def test_false_positive_creates_feedback_job(self, mock_delay):
        from rest_framework.test import APIClient
        from apps.alerts.models import Alert
        mock_delay.return_value = MagicMock(id="t1")
        analyst = make_user("ana@sentryx.local", role="analyst")
        alert = Alert.objects.create(owner=analyst, title="x", risk_score=80)
        client = APIClient()
        client.force_authenticate(analyst)
        resp = client.patch(f"/api/v1/alerts/{alert.pk}/", {"status": "false_pos"})
        self.assertEqual(resp.status_code, 200)
        job = RetrainingJob.objects.get()
        self.assertEqual(job.trigger, RetrainingJob.Trigger.FEEDBACK)
        self.assertEqual(job.triggered_by, analyst)
