"""
Sentryx v2 — Tests de integración del backend.
Cubre los endpoints principales sin llamar al ML Engine real
(se usa mock del cliente HTTP).
"""
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from apps.alerts.models   import Alert
from apps.audit.models    import AuditLog
from tests.utils          import make_user

User = get_user_model()

# ── Respuesta simulada del ML Engine ─────────────────────
MOCK_PHISHING_RESULT = {
    "risk_score":    82.5,
    "classification":"phishing",
    "phishing_type": "bec",
    "mitre_technique":"T1566.002",
    "mitre_tactic":  "Initial Access",
    "scores_by_layer":{"headers": 90.0, "content": 75.0, "urls": 85.0},
    "features_by_layer":{},
    "url_count":     2,
    "urls_analyzed": [{"url_truncated": "http://evil.tk/pay", "score": 85.0}],
    "model_versions":{"headers": "rf_v1", "content": "svm_v1", "urls": "rf_v1"},
    "weights":       {"headers": 0.35, "content": 0.40, "urls": 0.25},
}

MOCK_LEGIT_RESULT = {
    "risk_score":    8.0,
    "classification":"legitimate",
    "phishing_type": "legitimate",
    "mitre_technique":"T1566",
    "mitre_tactic":  "Initial Access",
    "scores_by_layer":{"headers": 5.0, "content": 8.0, "urls": 0.0},
    "features_by_layer":{},
    "url_count": 0, "urls_analyzed": [],
    "model_versions":{}, "weights":{},
}

SAMPLE_EMAIL = {
    "headers": {
        "from_addr": "attacker@evil.tk",
        "to_addr":   "tesoreria@empresa.co",
        "subject":   "Cambio de cuenta bancaria urgente",
        "authentication_results": "spf=fail dkim=none dmarc=fail",
    },
    "body_text": "Por favor actualiza el pago a la nueva cuenta bancaria. Urgente.",
}

ML_PATCH = "apps.alerts.views.analyze_email_sync"


def _alert(owner, **kw):
    defaults = dict(
        severity=Alert.Severity.HIGH, phishing_type="bec", title="Alerta",
        risk_score=75.0, score_headers=80.0, score_content=70.0, score_urls=75.0,
    )
    defaults.update(kw)
    return Alert.objects.create(owner=owner, **defaults)


class TestAuthEndpoints(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = make_user("analyst01@sentryx.local", role="analyst")

    def test_login_returns_tokens(self):
        resp = self.client.post("/api/v1/auth/token/", {
            "email": "analyst01@sentryx.local", "password": "SecurePass123!"
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)
        self.assertNotIn("mfa_required", resp.data)

    def test_login_wrong_password(self):
        resp = self.client.post("/api/v1/auth/token/", {
            "email": "analyst01@sentryx.local", "password": "wrong"
        })
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_pending_approval_returns_403(self):
        make_user("pendiente@sentryx.local", is_approved=False)
        resp = self.client.post("/api/v1/auth/token/", {
            "email": "pendiente@sentryx.local", "password": "SecurePass123!"
        })
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data["code"], "account_pending_approval")

    def test_me_returns_profile(self):
        self.client.force_authenticate(self.user)
        resp = self.client.get("/api/v1/auth/me/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["email"], "analyst01@sentryx.local")
        self.assertEqual(resp.data["role"], "analyst")

    def test_me_cannot_escalate_role(self):
        self.client.force_authenticate(self.user)
        resp = self.client.patch("/api/v1/auth/me/", {"role": "admin"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, "analyst")

    def test_unauthenticated_returns_401(self):
        resp = self.client.get("/api/v1/auth/me/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class TestAlertListEndpoint(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.viewer = make_user("viewer01@sentryx.local", role="viewer")
        self.other  = make_user("otro@sentryx.local", role="analyst")
        self.client.force_authenticate(self.viewer)

        for i, ptype in enumerate(["bec", "spear", "whaling"]):
            _alert(self.viewer, phishing_type=ptype, title=f"Alerta {i}")
        # Alerta de otro usuario: no debe aparecer (aislamiento por usuario)
        _alert(self.other, title="Ajena")

    def test_list_returns_only_own_alerts(self):
        resp = self.client.get("/api/v1/alerts/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 3)

    def test_admin_sees_all_alerts(self):
        admin = make_user("admin01@sentryx.local", role="admin")
        self.client.force_authenticate(admin)
        resp = self.client.get("/api/v1/alerts/")
        self.assertEqual(resp.data["count"], 4)

    def test_filter_by_phishing_type(self):
        resp = self.client.get("/api/v1/alerts/?phishing_type=bec")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)

    def test_filter_by_severity(self):
        resp = self.client.get("/api/v1/alerts/?severity=HIGH")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 3)

    def test_alert_detail_returns_correct_fields(self):
        alert = Alert.objects.filter(owner=self.viewer).first()
        resp  = self.client.get(f"/api/v1/alerts/{alert.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        for field in ("risk_score", "score_headers", "score_content", "score_urls"):
            self.assertIn(field, resp.data)
        # Verificar que no se expone información personal
        self.assertNotIn("sender_email", resp.data)

    def test_cannot_read_foreign_alert(self):
        foreign = Alert.objects.get(owner=self.other)
        resp = self.client.get(f"/api/v1/alerts/{foreign.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_viewer_cannot_update_alert(self):
        alert = Alert.objects.filter(owner=self.viewer).first()
        resp  = self.client.patch(f"/api/v1/alerts/{alert.pk}/", {"status": "resolved"})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_analyst_can_update_status(self):
        self.client.force_authenticate(self.other)
        alert = Alert.objects.get(owner=self.other)
        resp  = self.client.patch(f"/api/v1/alerts/{alert.pk}/", {"status": "acknowledged"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        alert.refresh_from_db()
        self.assertEqual(alert.status, "acknowledged")


class TestEmailAnalyzeEndpoint(TestCase):

    def setUp(self):
        self.client  = APIClient()
        self.analyst = make_user("analyst03@sentryx.local", role="analyst")
        self.client.force_authenticate(self.analyst)

    @patch(ML_PATCH, return_value=MOCK_PHISHING_RESULT)
    def test_phishing_email_creates_alert(self, mock_ml):
        resp = self.client.post("/api/v1/alerts/analyze/", SAMPLE_EMAIL, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(resp.data["alert_created"])
        self.assertIsNotNone(resp.data["alert_id"])
        self.assertEqual(resp.data["classification"], "phishing")

        alert = Alert.objects.get(pk=resp.data["alert_id"])
        self.assertEqual(alert.owner, self.analyst)
        self.assertEqual(alert.phishing_type, "bec")
        self.assertEqual(alert.risk_score, 82.5)
        # Remitente, destinatario, asunto y cuerpo solo como SHA-256 + salt
        for value in (alert.sender_hash, alert.recipient_hash,
                      alert.subject_hash, alert.email_body_hash):
            self.assertEqual(len(value), 64)
        self.assertNotIn("attacker", alert.sender_hash)
        self.assertEqual(alert.sender_domain, "evil.tk")

    @patch(ML_PATCH, return_value=MOCK_LEGIT_RESULT)
    def test_legitimate_email_no_alert(self, mock_ml):
        resp = self.client.post("/api/v1/alerts/analyze/", {
            "body_text": "Gracias por tu pedido en Amazon."
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data["alert_created"])
        self.assertIsNone(resp.data["alert_id"])

    def test_empty_body_returns_400(self):
        resp = self.client.post("/api/v1/alerts/analyze/", {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_viewer_cannot_analyze(self):
        viewer = make_user("viewer02@sentryx.local", role="viewer")
        self.client.force_authenticate(viewer)
        resp = self.client.post("/api/v1/alerts/analyze/", SAMPLE_EMAIL, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    @patch(ML_PATCH, return_value=MOCK_PHISHING_RESULT)
    def test_analyze_creates_audit_log(self, mock_ml):
        self.client.post("/api/v1/alerts/analyze/", SAMPLE_EMAIL, format="json")
        log = AuditLog.objects.filter(action=AuditLog.Action.ANALYZE).latest("occurred_at")
        self.assertEqual(log.username_snapshot, "analyst03")

    @patch(ML_PATCH, return_value=MOCK_PHISHING_RESULT)
    def test_campaign_created_after_3_alerts_same_domain(self, mock_ml):
        for _ in range(2):
            _alert(self.analyst, sender_domain="evil.tk", title="BEC previo")

        resp = self.client.post("/api/v1/alerts/analyze/", SAMPLE_EMAIL, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        alert = Alert.objects.get(pk=resp.data["alert_id"])
        self.assertIsNotNone(alert.campaign)
        self.assertEqual(alert.campaign.alert_count, 3)


class TestStatsEndpoint(TestCase):

    def setUp(self):
        self.client = APIClient()
        user = make_user("u@sentryx.local", role="viewer")
        self.client.force_authenticate(user)
        _alert(user, severity="CRITICAL", risk_score=90.0)

    def test_stats_returns_correct_structure(self):
        resp = self.client.get("/api/v1/alerts/stats/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        for key in ["total", "new", "critical", "by_severity",
                    "by_type", "daily_last_7_days", "active_campaigns"]:
            self.assertIn(key, resp.data)

    def test_stats_total_count(self):
        resp = self.client.get("/api/v1/alerts/stats/")
        self.assertEqual(resp.data["total"], 1)
        self.assertEqual(resp.data["critical"], 1)


class TestAuditLogImmutability(TestCase):

    def setUp(self):
        self.user = make_user("admin01@sentryx.local", role="admin")

    def test_cannot_modify_audit_log(self):
        log = AuditLog.log(AuditLog.Action.LOGIN, "auth", user=self.user)
        with self.assertRaises(PermissionError):
            log.action = "DELETE"
            log.save()

    def test_ip_stored_as_hash_not_plaintext(self):
        log = AuditLog.log(AuditLog.Action.LOGIN, "auth",
                           user=self.user, ip="192.168.1.100")
        self.assertNotEqual(log.ip_hash, "192.168.1.100")
        self.assertEqual(len(log.ip_hash), 64)
