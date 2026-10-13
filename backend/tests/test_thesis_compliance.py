"""
Pruebas de lo que afirma la tesis: seudonimización, retención, correlación de
campañas, umbrales y pesos, informes con auditoría EXPORT y aislamiento.
"""
import hashlib
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.alerts.models import Alert
from apps.alerts.pseudonymize import pseudonymize_email, pseudonymize_subject
from apps.alerts.service import create_alert_from_ml_result
from apps.alerts.tasks import purge_old_data_task
from apps.audit.models import AuditLog
from apps.incidents.models import Incident
from tests.utils import make_user

ML_RESULT = {
    "risk_score": 80.0, "classification": "phishing", "phishing_type": "bec",
    "mitre_technique": "T1566.002", "scores_by_layer": {"headers": 80, "content": 80, "urls": 80},
    "urls_analyzed": [], "url_count": 0, "features_by_layer": {},
}


def payload(sender="ceo@evil.tk", to="tesoreria@empresa.co", subject="Pago urgente"):
    return {"headers": {"from": sender, "to": to, "subject": subject},
            "body_text": "Transfiere hoy."}


class TestPseudonymization(TestCase):

    def test_sha256_with_salt(self):
        expected = hashlib.sha256(
            f"tesoreria@empresa.co{settings.PSEUDONYMIZATION_SALT}".encode()).hexdigest()
        self.assertEqual(pseudonymize_email("Tesoreria@Empresa.co "), expected)

    def test_alert_stores_only_hashes(self):
        user = make_user("a@sentryx.local")
        alert = create_alert_from_ml_result(ML_RESULT, payload(), owner=user)
        self.assertEqual(alert.sender_hash, pseudonymize_email("ceo@evil.tk"))
        self.assertEqual(alert.recipient_hash, pseudonymize_email("tesoreria@empresa.co"))
        self.assertEqual(alert.subject_hash, pseudonymize_subject("Pago urgente"))
        self.assertEqual(len(alert.email_body_hash), 64)
        stored = " ".join(str(v) for v in Alert.objects.filter(pk=alert.pk).values().first().values())
        for plain in ("ceo@evil.tk", "tesoreria@empresa.co", "Pago urgente", "Transfiere hoy"):
            self.assertNotIn(plain, stored)


class TestRetention(TestCase):

    def _alert(self, status, days_old):
        a = Alert.objects.create(title="x", status=status, risk_score=50)
        Alert.objects.filter(pk=a.pk).update(detected_at=timezone.now() - timedelta(days=days_old))
        return a

    def test_purges_closed_alerts_after_90_days_and_audit_after_365(self):
        old_resolved = self._alert("resolved", 91)
        recent_resolved = self._alert("resolved", 89)
        old_open = self._alert("new", 200)
        log_old = AuditLog.log(AuditLog.Action.LOGIN, "auth")
        log_new = AuditLog.log(AuditLog.Action.LOGIN, "auth")
        AuditLog.objects.filter(pk=log_old.pk).update(
            occurred_at=timezone.now() - timedelta(days=366))

        result = purge_old_data_task()

        self.assertEqual(result["deleted_alerts"], 1)
        self.assertFalse(Alert.objects.filter(pk=old_resolved.pk).exists())
        self.assertTrue(Alert.objects.filter(pk=recent_resolved.pk).exists())
        self.assertTrue(Alert.objects.filter(pk=old_open.pk).exists())
        self.assertFalse(AuditLog.objects.filter(pk=log_old.pk).exists())
        self.assertTrue(AuditLog.objects.filter(pk=log_new.pk).exists())


class TestCampaignCorrelation(TestCase):

    def test_three_alerts_same_domain_within_one_hour(self):
        user = make_user("c@sentryx.local")
        for _ in range(3):
            alert = create_alert_from_ml_result(ML_RESULT, payload(), owner=user)
        self.assertIsNotNone(alert.campaign)
        alert.campaign.refresh_from_db()   # alert_count se actualiza con update()
        self.assertEqual(alert.campaign.alert_count, 3)

    def test_alerts_older_than_one_hour_do_not_count(self):
        user = make_user("c2@sentryx.local")
        for _ in range(2):
            a = create_alert_from_ml_result(ML_RESULT, payload(), owner=user)
            Alert.objects.filter(pk=a.pk).update(detected_at=timezone.now() - timedelta(minutes=61))
        alert = create_alert_from_ml_result(ML_RESULT, payload(), owner=user)
        self.assertIsNone(alert.campaign)

    def test_campaign_does_not_absorb_other_users_alerts(self):
        ana, luis = make_user("ana@sentryx.local"), make_user("luis@sentryx.local")
        foreign = create_alert_from_ml_result(ML_RESULT, payload(), owner=luis)
        for _ in range(3):
            create_alert_from_ml_result(ML_RESULT, payload(), owner=ana)
        foreign.refresh_from_db()
        self.assertIsNone(foreign.campaign)


class TestThresholdsAndWeights(TestCase):

    def test_settings(self):
        self.assertEqual(settings.ML_THRESHOLDS,
                         {"suspicious": 40, "phishing": 70, "critical": 85})
        self.assertEqual(settings.ML_WEIGHTS, {"headers": 0.35, "content": 0.40, "urls": 0.25})

    def test_severity_boundaries(self):
        from apps.alerts.service import _severity_from_score
        self.assertEqual(_severity_from_score(39.9), Alert.Severity.LOW)
        self.assertEqual(_severity_from_score(40), Alert.Severity.MEDIUM)
        self.assertEqual(_severity_from_score(70), Alert.Severity.HIGH)
        self.assertEqual(_severity_from_score(85), Alert.Severity.CRITICAL)


class TestReportsAudit(TestCase):

    def test_pdf_and_csv_exports_are_audited(self):
        user = make_user("r@sentryx.local")
        client = APIClient()
        client.force_authenticate(user)
        for export, ctype in (("csv", "text/csv"), ("pdf", "application/pdf")):
            resp = client.get("/api/v1/alerts/report/", {"period": "weekly", "export": export})
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp["Content-Type"].startswith(ctype))
        logs = AuditLog.objects.filter(action=AuditLog.Action.EXPORT, resource="reports")
        self.assertEqual(sorted(logs.values_list("detail__export", flat=True)), ["csv", "pdf"])


class TestIncidentIsolation(TestCase):

    def setUp(self):
        self.ana  = make_user("ana@sentryx.local")
        self.luis = make_user("luis@sentryx.local")
        self.admin = make_user("admin@sentryx.local", role="admin")
        self.own = Incident.objects.create(title="De Ana", created_by=self.ana)
        self.foreign = Incident.objects.create(title="De Luis", created_by=self.luis)
        self.client = APIClient()

    def test_analyst_sees_only_own_or_assigned(self):
        Incident.objects.create(title="Asignado a Ana", created_by=self.luis, assigned_to=self.ana)
        self.client.force_authenticate(self.ana)
        titles = {i["title"] for i in self.client.get("/api/v1/incidents/").data["results"]}
        self.assertEqual(titles, {"De Ana", "Asignado a Ana"})
        self.assertEqual(self.client.get(f"/api/v1/incidents/{self.foreign.pk}/").status_code, 404)

    def test_admin_sees_all(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/api/v1/incidents/").data["count"], 2)

    def test_cannot_attach_other_users_alerts(self):
        foreign_alert = Alert.objects.create(title="x", owner=self.luis, risk_score=80)
        self.client.force_authenticate(self.ana)
        resp = self.client.post("/api/v1/incidents/", {
            "title": "Intento", "severity": "HIGH", "alert_ids": [str(foreign_alert.pk)],
        }, format="json")
        self.assertEqual(resp.status_code, 400)


class TestViewerRole(TestCase):

    @patch("apps.alerts.views.analyze_email_sync", return_value=ML_RESULT)
    def test_viewer_is_read_only(self, _):
        viewer = make_user("v@sentryx.local", role="viewer")
        alert = Alert.objects.create(title="x", owner=viewer, risk_score=80)
        client = APIClient()
        client.force_authenticate(viewer)
        self.assertEqual(client.get("/api/v1/alerts/").status_code, 200)
        self.assertEqual(client.patch(f"/api/v1/alerts/{alert.pk}/", {"status": "resolved"}).status_code, 403)
        self.assertEqual(client.post("/api/v1/alerts/analyze/", {"body_text": "x"}, format="json").status_code, 403)
        self.assertEqual(client.post("/api/v1/incidents/", {"title": "x"}, format="json").status_code, 403)
