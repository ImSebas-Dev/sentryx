"""Pruebas del registro de tareas programadas (migración alerts/0005)."""
from django.conf import settings
from django.test import TestCase
from django_celery_beat.models import (
    PeriodicTask, PeriodicTasks, IntervalSchedule, CrontabSchedule,
)

from config.beat_schedule import register_periodic_tasks

EXPECTED = {
    "purge_old_data":  "alerts.purge_old_data",
    "sync_phishtank":  "threat_intel.sync_phishtank",
    "sync_openphish":  "threat_intel.sync_openphish",
    "monthly_retrain": "ml_feedback.monthly_retrain",
}


class TestBeatSchedule(TestCase):

    def test_migration_registers_all_tasks(self):
        tasks = dict(PeriodicTask.objects.filter(name__in=EXPECTED)
                     .values_list("name", "task"))
        self.assertEqual(tasks, EXPECTED)

    def test_purge_runs_daily_at_2am_bogota(self):
        cron = PeriodicTask.objects.get(name="purge_old_data").crontab
        self.assertEqual((cron.minute, cron.hour, cron.day_of_month), ("0", "2", "*"))
        self.assertEqual(str(cron.timezone), "America/Bogota")

    def test_monthly_retrain_runs_day_1_at_3am(self):
        cron = PeriodicTask.objects.get(name="monthly_retrain").crontab
        self.assertEqual((cron.minute, cron.hour, cron.day_of_month), ("0", "3", "1"))
        self.assertEqual(str(cron.timezone), "America/Bogota")

    def test_feeds_use_configured_intervals(self):
        pt = PeriodicTask.objects.get(name="sync_phishtank")
        op = PeriodicTask.objects.get(name="sync_openphish")
        self.assertEqual(pt.interval.every, settings.PHISHTANK_SYNC_INTERVAL_HOURS)
        self.assertEqual(op.interval.every, settings.OPENPHISH_SYNC_INTERVAL_HOURS)
        self.assertEqual(pt.queue, "threat_intel")

    def test_registration_is_idempotent(self):
        before = PeriodicTask.objects.count()
        register_periodic_tasks(settings, PeriodicTask, IntervalSchedule,
                                CrontabSchedule, PeriodicTasks)
        self.assertEqual(PeriodicTask.objects.count(), before)
