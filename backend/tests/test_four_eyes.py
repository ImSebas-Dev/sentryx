"""Pruebas del control de cuatro ojos: disparadores, reglas de seguridad y auditoría."""
import threading
from datetime import timedelta
from unittest.mock import patch

import pyotp
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.alerts.models import Alert
from apps.audit.models import AuditLog
from apps.four_eyes import detectors, services
from apps.four_eyes.models import ApprovalRequest, FourEyesPolicy
from apps.four_eyes.tasks import expire_requests_task
from apps.payment_shield.models import PaymentCheck
from apps.users import mfa
from tests.test_payment_shield import ML_LOW, make_supplier
from tests.utils import make_user

ORG = "Acme SAS"
ML_PATCH = "apps.alerts.views.analyze_email_sync"
SEND_PATCH = "apps.four_eyes.services.send_notification"
ML_HIGH = {**ML_LOW, "risk_score": 75.0, "classification": "phishing", "phishing_type": "spear"}
REASONS = [{"trigger": "payment", "detail": "pide pagar a una cuenta que no coincide con Proveedor X"}]


def enable_mfa(user):
    setup = mfa.start_setup(user)
    mfa.enable(user)
    return setup["secret"]


def make_alert(owner, severity="HIGH", required=True):
    signals = {"four_eyes": {"required": True, "reasons": REASONS}} if required else {}
    return Alert.objects.create(owner=owner, severity=severity, phishing_type="bec", title="Alerta",
                                risk_score=75.0, sender_domain="evil.tk", risk_signals=signals)


class TestDetectors(TestCase):

    def test_credentials(self):
        self.assertTrue(detectors.detect_credential_request("Debes INICIAR SESIÓN aquí"))
        self.assertTrue(detectors.detect_credential_request("Verifica tu cuenta hoy"))
        self.assertTrue(detectors.detect_credential_request(
            "Entra a http://evil.tk/wp-login.php"))
        self.assertTrue(detectors.detect_credential_request(
            "", '<form><input type="password" name="p"></form>'))
        self.assertFalse(detectors.detect_credential_request("Nos vemos el lunes"))

    def test_risky_attachments(self):
        for name in ("a.exe", "a.JS", "a.vbs", "a.scr", "a.iso", "a.lnk", "a.html", "a.htm",
                     "a.docm", "a.xlsm"):
            self.assertEqual(detectors.detect_risky_attachments([name]), [name])
        self.assertEqual(detectors.detect_risky_attachments(["factura.pdf", "foto.png", "x.zip"]), [])

    def test_zip_or_rar_with_password_hint(self):
        self.assertEqual(detectors.detect_risky_attachments(
            ["x.rar"], body_text="La contraseña es 1234"), ["x.rar"])

    def test_encrypted_zip_is_detected_from_bytes(self):
        import zipfile, io
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            archive.writestr("a.txt", "x")
        raw = bytearray(buf.getvalue())
        # Marca el bit de cifrado en los encabezados local y central del ZIP
        raw[6] |= 1
        central = raw.find(b"PK\x01\x02")
        raw[central + 8] |= 1
        upload = SimpleUploadedFile("x.zip", bytes(raw))
        self.assertEqual(detectors.detect_risky_attachments(["x.zip"], [upload]), ["x.zip"])


class TestPolicyEvaluation(TestCase):
    URL = "/api/v1/alerts/analyze/"

    def setUp(self):
        self.client = APIClient()
        self.analyst = make_user("ana@acme.co", organization=ORG)
        self.client.force_authenticate(self.analyst)
        make_supplier()

    def analyze(self, body, sender="x@evil.tk", **extra):
        return self.client.post(self.URL, {
            "headers": {"from_addr": sender}, "body_text": body, **extra}, format="json")

    @patch(ML_PATCH, return_value=ML_LOW)
    def test_payment_trigger(self, _):
        resp = self.analyze("Actualizamos nuestros datos bancarios", sender="p@proveedor.com")
        self.assertTrue(resp.data["four_eyes_required"])
        self.assertEqual(resp.data["four_eyes_reasons"][0]["trigger"], "payment")
        self.assertIn("Proveedor Uno", resp.data["four_eyes_reasons"][0]["detail"])
        alert = Alert.objects.get(pk=resp.data["alert_id"])
        self.assertTrue(alert.risk_signals["four_eyes"]["required"])
        self.assertEqual(alert.risk_score, 12.0)

    @patch(ML_PATCH, return_value=ML_HIGH)
    def test_credentials_trigger(self, _):
        resp = self.analyze("Verifica tu cuenta para no perder el acceso")
        self.assertEqual(resp.data["four_eyes_reasons"][0]["trigger"], "credentials")

    @patch(ML_PATCH, return_value=ML_HIGH)
    def test_attachments_trigger(self, _):
        resp = self.analyze("Revisa el documento", attachment_names=["orden.docm"])
        self.assertEqual(resp.data["four_eyes_reasons"][0]["trigger"], "attachments")
        self.assertIn("orden.docm", resp.data["four_eyes_reasons"][0]["detail"])

    @patch(ML_PATCH, return_value={**ML_LOW, "risk_score": 45.0, "classification": "suspicious"})
    def test_low_severity_does_not_trigger(self, _):
        resp = self.analyze("Verifica tu cuenta")
        self.assertEqual(resp.data["severity"], "MEDIUM")
        self.assertFalse(resp.data["four_eyes_required"])

    @patch(ML_PATCH, return_value=ML_LOW)
    def test_legit_mail_without_alert_does_not_trigger(self, _):
        resp = self.analyze("Verifica tu cuenta")
        self.assertFalse(resp.data["alert_created"])
        self.assertFalse(resp.data["four_eyes_required"])

    @patch(ML_PATCH, return_value=ML_HIGH)
    def test_high_severity_without_trigger(self, _):
        self.assertFalse(self.analyze("Hola, buen día").data["four_eyes_required"])

    @patch(ML_PATCH, return_value=ML_HIGH)
    def test_disabled_policy_and_switches(self, _):
        policy = services.policy_for(ORG)
        policy.require_for_credentials = False
        policy.save()
        self.assertFalse(self.analyze("Verifica tu cuenta").data["four_eyes_required"])
        policy.require_for_credentials = True
        policy.enabled = False
        policy.save()
        self.assertFalse(self.analyze("Verifica tu cuenta").data["four_eyes_required"])

    @patch(ML_PATCH, return_value={**ML_HIGH, "risk_score": 90.0, "classification": "critical"})
    def test_min_severity_is_respected(self, _):
        policy = services.policy_for(ORG)
        policy.min_severity = "CRITICAL"
        policy.save()
        self.assertTrue(self.analyze("Verifica tu cuenta").data["four_eyes_required"])

    @patch(ML_PATCH, return_value=ML_HIGH)
    def test_user_without_org_is_not_blocked(self, _):
        self.client.force_authenticate(make_user("solo@x.co"))
        self.assertFalse(self.analyze("Verifica tu cuenta").data["four_eyes_required"])

    def test_policy_is_created_with_defaults(self):
        policy = services.policy_for("Nueva SAS")
        self.assertTrue(policy.enabled and policy.require_mfa_for_approval)
        self.assertEqual(policy.min_severity, "HIGH")
        self.assertEqual(policy.expiry_minutes, 240)


class FourEyesCase(TestCase):

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.requester = make_user("ana@acme.co", organization=ORG)
        self.admin = make_user("jefa@acme.co", role="admin", organization=ORG)
        self.secret = enable_mfa(self.admin)
        self.outsider = make_user("jefe@otra.co", role="admin", organization="Otra SAS")
        self.alert = make_alert(self.requester)
        self.send = patch(SEND_PATCH, return_value=True)
        self.sent = self.send.start()
        self.addCleanup(self.send.stop)

    def login(self, user):
        self.client.force_authenticate(user)

    def new_request(self, **extra):
        request_obj, _ = services.create_request(self.alert, self.requester, "porfa")
        for key, value in extra.items():
            setattr(request_obj, key, value)
        request_obj.save()
        return request_obj

    def url(self, request_obj, action):
        return f"/api/v1/four-eyes/requests/{request_obj.pk}/{action}/"

    def code(self):
        cache.clear()  # Permite usar el código actual más de una vez en la misma prueba
        return pyotp.TOTP(self.secret).now()

    def approve(self, request_obj, user=None, **data):
        self.login(user or self.admin)
        data.setdefault("totp_code", self.code())
        return self.client.post(self.url(request_obj, "approve"), data, format="json")

    def denied(self, reason):
        return AuditLog.objects.filter(action="FOUR_EYES_DENIED", detail__reason=reason).exists()


class TestCreateRequest(FourEyesCase):
    URL = "/api/v1/four-eyes/requests/"

    def test_owner_creates_and_approvers_are_notified_without_content(self):
        self.login(self.requester)
        resp = self.client.post(self.URL, {"alert_id": str(self.alert.pk), "note": "Urgente"},
                                format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["status"], "pending")
        self.assertEqual(resp.data["reasons"], REASONS)
        self.assertTrue(AuditLog.objects.filter(action="FOUR_EYES_REQUESTED").exists())
        self.sent.assert_called_once()
        to, subject, html, text = self.sent.call_args[0]
        self.assertEqual(to, self.admin.email)
        self.assertIn("no coincide con Proveedor X", html)

    def test_second_click_returns_same_pending(self):
        self.login(self.requester)
        first = self.client.post(self.URL, {"alert_id": str(self.alert.pk)}, format="json")
        second = self.client.post(self.URL, {"alert_id": str(self.alert.pk)}, format="json")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["id"], second.data["id"])

    def test_analyst_of_same_org_can_request(self):
        colleague = make_user("beto@acme.co", organization=ORG)
        self.login(colleague)
        resp = self.client.post(self.URL, {"alert_id": str(self.alert.pk)}, format="json")
        self.assertEqual(resp.status_code, 201)

    def test_viewer_not_owner_cannot_request(self):
        viewer = make_user("vera@acme.co", role="viewer", organization=ORG)
        self.login(viewer)
        resp = self.client.post(self.URL, {"alert_id": str(self.alert.pk)}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_other_org_is_rejected_and_audited(self):
        self.login(self.outsider)
        resp = self.client.post(self.URL, {"alert_id": str(self.alert.pk)}, format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data["code"], "other_organization")
        self.assertTrue(self.denied("other_organization"))

    def test_alert_that_does_not_require_it(self):
        alert = make_alert(self.requester, required=False)
        self.login(self.requester)
        resp = self.client.post(self.URL, {"alert_id": str(alert.pk)}, format="json")
        self.assertEqual(resp.status_code, 409)

    def test_sole_approver_gets_clear_error(self):
        boss = make_user("unica@solo.co", role="admin", organization="Solo SAS")
        alert = make_alert(boss)
        self.login(boss)
        resp = self.client.post(self.URL, {"alert_id": str(alert.pk)}, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "no_other_approver")
        self.assertIn("otra persona", resp.data["error"])

    def test_expired_pending_can_be_requested_again(self):
        old = self.new_request(expires_at=timezone.now() - timedelta(minutes=1))
        self.login(self.requester)
        resp = self.client.post(self.URL, {"alert_id": str(self.alert.pk)}, format="json")
        self.assertEqual(resp.status_code, 201)
        old.refresh_from_db()
        self.assertEqual(old.status, "expired")

    def test_unique_constraint_only_for_pending(self):
        first = self.new_request()
        first.status = "cancelled"
        first.save()
        self.assertTrue(self.new_request().pk != first.pk)


class TestDecisionRules(FourEyesCase):

    def test_approve_with_totp(self):
        request_obj = self.new_request()
        resp = self.approve(request_obj, note="Lo revisé")
        self.assertEqual(resp.status_code, 200, resp.data)
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, "approved")
        self.assertEqual(request_obj.decided_by, self.admin)
        self.assertIsNotNone(request_obj.decided_at)
        self.assertTrue(AuditLog.objects.filter(action="FOUR_EYES_APPROVED").exists())

    def test_self_approval_blocked_even_for_admin(self):
        other_admin = make_user("otra@acme.co", role="admin", organization=ORG)
        secret = enable_mfa(other_admin)
        alert = make_alert(other_admin)
        request_obj, _ = services.create_request(alert, other_admin)
        self.login(other_admin)
        cache.clear()
        resp = self.client.post(self.url(request_obj, "approve"),
                                {"totp_code": pyotp.TOTP(secret).now()}, format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data["code"], "self_approval")
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, "pending")
        self.assertTrue(self.denied("self_approval"))

    def test_self_reject_blocked_too(self):
        admin_requester = make_user("otra@acme.co", role="admin", organization=ORG)
        request_obj, _ = services.create_request(make_alert(admin_requester), admin_requester)
        self.login(admin_requester)
        resp = self.client.post(self.url(request_obj, "reject"), {"note": "No"}, format="json")
        self.assertEqual(resp.data["code"], "self_approval")

    def test_sole_approver_self_decision_explains_need(self):
        request_obj = self.new_request()
        policy = services.policy_for(ORG)
        policy.approvers.set([self.requester])
        self.login(self.requester)
        resp = self.client.post(self.url(request_obj, "approve"), {"totp_code": "1"}, format="json")
        self.assertEqual(resp.data["code"], "no_other_approver")

    def test_other_organization_blocked_and_audited(self):
        request_obj = self.new_request()
        secret = enable_mfa(self.outsider)
        self.login(self.outsider)
        cache.clear()
        resp = self.client.post(self.url(request_obj, "approve"),
                                {"totp_code": pyotp.TOTP(secret).now()}, format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data["code"], "other_organization")
        self.assertTrue(self.denied("other_organization"))

    def test_analyst_not_in_list_cannot_approve(self):
        colleague = make_user("beto@acme.co", organization=ORG)
        resp = self.approve(self.new_request(), user=colleague)
        self.assertEqual(resp.data["code"], "not_approver")

    def test_admin_not_in_explicit_list_cannot_approve(self):
        colleague = make_user("beto@acme.co", organization=ORG)
        services.policy_for(ORG).approvers.set([colleague])
        resp = self.approve(self.new_request())
        self.assertEqual(resp.data["code"], "not_approver")

    def test_listed_approver_can_approve(self):
        colleague = make_user("beto@acme.co", role="viewer", organization=ORG)
        secret = enable_mfa(colleague)
        services.policy_for(ORG).approvers.set([colleague])
        request_obj = self.new_request()
        self.login(colleague)
        cache.clear()
        resp = self.client.post(self.url(request_obj, "approve"),
                                {"totp_code": pyotp.TOTP(secret).now()}, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)

    def test_invalid_totp_rejected_and_audited(self):
        request_obj = self.new_request()
        resp = self.approve(request_obj, totp_code="000000")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "invalid_totp")
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, "pending")
        self.assertTrue(self.denied("invalid_totp"))

    def test_missing_totp_rejected(self):
        self.login(self.admin)
        resp = self.client.post(self.url(self.new_request(), "approve"), {}, format="json")
        self.assertEqual(resp.data["code"], "invalid_totp")

    def test_approver_without_mfa_rejected(self):
        no_mfa = make_user("sinmfa@acme.co", role="admin", organization=ORG)
        resp = self.approve(self.new_request(), user=no_mfa, totp_code="123456")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data["code"], "mfa_required")
        self.assertIn("verificación en dos pasos", resp.data["error"])

    def test_policy_without_mfa_does_not_ask_for_code(self):
        policy = services.policy_for(ORG)
        policy.require_mfa_for_approval = False
        policy.save()
        no_mfa = make_user("sinmfa@acme.co", role="admin", organization=ORG)
        self.login(no_mfa)
        resp = self.client.post(self.url(self.new_request(), "approve"), {}, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)

    def test_reject_requires_note(self):
        request_obj = self.new_request()
        self.login(self.admin)
        resp = self.client.post(self.url(request_obj, "reject"),
                                {"totp_code": self.code()}, format="json")
        self.assertEqual(resp.data["code"], "note_required")

    def test_reject_offers_guided_response(self):
        request_obj = self.new_request()
        self.login(self.admin)
        resp = self.client.post(self.url(request_obj, "reject"),
                                {"totp_code": self.code(), "note": "Es fraude"}, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["guided_response"]["question"], "¿Ya hiciste clic o pagaste?")
        self.assertIn(str(self.alert.pk), resp.data["guided_response"]["url"])
        self.assertTrue(AuditLog.objects.filter(action="FOUR_EYES_REJECTED").exists())
        to, subject, html, text = self.sent.call_args[0]
        self.assertEqual(to, self.requester.email)
        self.assertIn("¿Ya hiciste clic o pagaste?", html)
        self.assertIn(f"/respond?alert={self.alert.pk}", text)

    def test_cannot_decide_twice(self):
        request_obj = self.new_request()
        self.approve(request_obj)
        resp = self.approve(request_obj)
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "already_decided")

    def test_cancelled_cannot_be_decided(self):
        request_obj = self.new_request(status="cancelled")
        self.assertEqual(self.approve(request_obj).status_code, 409)

    def test_expired_cannot_be_decided_and_stays_expired(self):
        request_obj = self.new_request(expires_at=timezone.now() - timedelta(minutes=1))
        resp = self.approve(request_obj)
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "expired")
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, "expired")

    def test_notification_email_does_not_approve_by_get(self):
        request_obj = self.new_request()
        html = self.sent.call_args[0][2]
        self.assertIn(f"/approvals/{request_obj.pk}", html)
        self.assertNotIn("approve", html)
        self.assertNotIn("token", html)
        # Un GET al endpoint, con o sin sesión, nunca decide
        self.assertEqual(self.client.get(self.url(request_obj, "approve")).status_code, 401)
        self.login(self.admin)
        self.assertEqual(self.client.get(self.url(request_obj, "approve")).status_code, 405)
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, "pending")

    def test_anonymous_cannot_approve(self):
        request_obj = self.new_request()
        self.assertEqual(self.client.post(self.url(request_obj, "approve")).status_code, 401)

    def test_notification_failure_does_not_undo_decision(self):
        request_obj = self.new_request()
        self.sent.return_value = False
        self.assertEqual(self.approve(request_obj).status_code, 200)


class TestCancelStatusList(FourEyesCase):

    def test_cancel_only_by_requester(self):
        request_obj = self.new_request()
        self.login(self.admin)
        self.assertEqual(self.client.post(self.url(request_obj, "cancel")).status_code, 403)
        self.login(self.requester)
        self.assertEqual(self.client.post(self.url(request_obj, "cancel")).status_code, 200)
        self.assertEqual(self.client.post(self.url(request_obj, "cancel")).status_code, 409)
        self.assertTrue(AuditLog.objects.filter(action="FOUR_EYES_CANCELLED").exists())

    def test_status_is_light_and_scoped(self):
        request_obj = self.new_request()
        self.login(self.requester)
        resp = self.client.get(self.url(request_obj, "status"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(set(resp.data), {"id", "status", "decided_by_name", "decided_at",
                                          "decision_note", "expires_at"})
        self.login(self.outsider)
        self.assertEqual(self.client.get(self.url(request_obj, "status")).status_code, 404)

    def test_status_shows_expired_before_task_runs(self):
        request_obj = self.new_request(expires_at=timezone.now() - timedelta(seconds=1))
        self.login(self.requester)
        self.assertEqual(self.client.get(self.url(request_obj, "status")).data["status"], "expired")

    def test_status_has_own_throttle(self):
        from apps.four_eyes.views import RequestStatusView
        from django.conf import settings
        self.assertEqual(RequestStatusView.throttle_scope, "four_eyes_status")
        self.assertIn("four_eyes_status", settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"])

    def test_list_filters(self):
        mine = self.new_request()
        self.login(self.requester)
        base = "/api/v1/four-eyes/requests/"
        self.assertEqual(len(self.client.get(base, {"mine": "true"}).data), 1)
        self.assertEqual(len(self.client.get(base, {"to_approve": "true"}).data), 0)
        self.login(self.admin)
        self.assertEqual(self.client.get(base, {"to_approve": "true"}).data[0]["id"], str(mine.pk))
        self.assertTrue(self.client.get(base, {"to_approve": "true"}).data[0]["can_decide"])
        self.assertEqual(len(self.client.get(base, {"mine": "true"}).data), 0)
        self.assertEqual(len(self.client.get(base, {"status": "approved"}).data), 0)
        self.assertEqual(len(self.client.get(base, {"alert": str(self.alert.pk)}).data), 1)
        self.login(self.outsider)
        self.assertEqual(len(self.client.get(base).data), 0)
        self.assertEqual(self.client.get(f"{base}{mine.pk}/").status_code, 404)

    def test_requester_does_not_see_others_request(self):
        self.new_request()
        colleague = make_user("beto@acme.co", organization=ORG)
        self.login(colleague)
        self.assertEqual(len(self.client.get("/api/v1/four-eyes/requests/").data), 0)

    def test_stats(self):
        request_obj = self.new_request()
        self.login(self.admin)
        self.assertEqual(self.client.get("/api/v1/four-eyes/stats/").data["pending_to_approve"], 1)
        self.approve(request_obj)
        stats = self.client.get("/api/v1/four-eyes/stats/").data
        self.assertEqual((stats["month_total"], stats["approved"], stats["pending_to_approve"]),
                         (1, 1, 0))
        self.assertIsNotNone(stats["avg_decision_minutes"])


class TestPolicyApi(FourEyesCase):
    URL = "/api/v1/four-eyes/policy/"

    def test_get_creates_defaults(self):
        self.login(self.requester)
        resp = self.client.get(self.URL)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["enabled"])
        self.assertEqual(resp.data["candidates"], [])

    def test_only_admin_edits_and_is_audited(self):
        self.login(self.requester)
        self.assertEqual(self.client.put(self.URL, {"enabled": False}, format="json").status_code, 403)
        self.login(self.admin)
        resp = self.client.put(self.URL, {"enabled": False, "expiry_minutes": 60}, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        policy = FourEyesPolicy.objects.get(organization=ORG)
        self.assertFalse(policy.enabled)
        self.assertEqual(policy.expiry_minutes, 60)
        self.assertTrue(AuditLog.objects.filter(action="FOUR_EYES_POLICY_CHANGED").exists())

    def test_approvers_must_be_same_org(self):
        self.login(self.admin)
        resp = self.client.put(self.URL, {"approver_ids": [str(self.outsider.pk)]}, format="json")
        self.assertEqual(resp.status_code, 400)
        resp = self.client.put(self.URL, {"approver_ids": [str(self.requester.pk)]}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["approvers"][0]["username"], self.requester.username)

    def test_policy_is_isolated(self):
        self.login(self.outsider)
        self.client.put(self.URL, {"enabled": False}, format="json")
        self.assertTrue(services.policy_for(ORG).enabled)

    def test_candidates_only_for_admin(self):
        self.login(self.admin)
        emails = [c["email"] for c in self.client.get(self.URL).data["candidates"]]
        self.assertIn(self.requester.email, emails)
        self.assertNotIn(self.outsider.email, emails)


class TestExpiration(FourEyesCase):

    def test_task_expires_notifies_and_escalates(self):
        request_obj = self.new_request(expires_at=timezone.now() - timedelta(minutes=1))
        keep = make_alert(self.requester)
        alive, _ = services.create_request(keep, self.requester)
        self.sent.reset_mock()
        result = expire_requests_task()
        self.assertEqual(result["expired"], 1)
        request_obj.refresh_from_db()
        alive.refresh_from_db()
        self.assertEqual(request_obj.status, "expired")
        self.assertEqual(alive.status, "pending")
        recipients = [c.args[0] for c in self.sent.call_args_list]
        self.assertIn(self.requester.email, recipients)
        self.assertIn(self.admin.email, recipients)
        self.assertTrue(AuditLog.objects.filter(action="FOUR_EYES_EXPIRED",
                                                username_snapshot="system").exists())

    def test_beat_task_is_registered(self):
        from django_celery_beat.models import PeriodicTask
        task = PeriodicTask.objects.get(name="four_eyes_expire_requests")
        self.assertEqual(task.task, "four_eyes.expire_requests")
        self.assertEqual((task.interval.every, task.interval.period), (5, "minutes"))


class TestPaymentIntegration(FourEyesCase):

    def setUp(self):
        super().setUp()
        self.check = PaymentCheck.objects.create(
            alert=self.alert, owner=self.requester, organization=ORG, intent_detected=True,
            verdict=PaymentCheck.Verdict.ACCOUNT_MISMATCH)
        self.verify_url = f"/api/v1/payment-shield/checks/{self.check.pk}/verify/"
        self.login(self.requester)

    def verify(self, result):
        return self.client.post(self.verify_url, {"result": result}, format="json")

    def test_approved_needs_approval_request(self):
        resp = self.verify("approved")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "four_eyes_required")
        self.check.refresh_from_db()
        self.assertEqual(self.check.status, "pending_verification")

    def test_pending_request_is_not_enough(self):
        self.new_request()
        self.login(self.requester)
        self.assertEqual(self.verify("approved").status_code, 409)

    def test_approved_accepted_after_second_person(self):
        request_obj = self.new_request()
        self.approve(request_obj)
        self.login(self.requester)
        self.assertEqual(self.verify("approved").status_code, 200)

    def test_call_and_reject_do_not_need_it(self):
        self.assertEqual(self.verify("verified_by_call").status_code, 200)
        self.assertEqual(self.verify("rejected").status_code, 200)

    def test_disabled_policy_does_not_gate(self):
        policy = services.policy_for(ORG)
        policy.enabled = False
        policy.save()
        self.assertEqual(self.verify("approved").status_code, 200)

    def test_acknowledge_blocked_when_four_eyes_applies(self):
        url = f"/api/v1/payment-shield/checks/{self.check.pk}/acknowledge-risk/"
        self.assertEqual(self.client.post(url).status_code, 409)
        self.alert.risk_signals = {}
        self.alert.save()
        self.assertEqual(self.client.post(url).status_code, 200)

    def test_request_links_payment_check(self):
        self.assertEqual(self.new_request().payment_check, self.check)


class TestConcurrentDecision(TransactionTestCase):

    def test_only_one_decision_wins(self):
        requester = make_user("ana@acme.co", organization=ORG)
        first = make_user("uno@acme.co", role="admin", organization=ORG)
        second = make_user("dos@acme.co", role="admin", organization=ORG)
        FourEyesPolicy.objects.create(organization=ORG, require_mfa_for_approval=False)
        alert = make_alert(requester)
        with patch(SEND_PATCH, return_value=True):
            request_obj, _ = services.create_request(alert, requester)

        barrier = threading.Barrier(2)
        outcomes = []

        def worker(actor, approve):
            try:
                barrier.wait(timeout=5)
                with patch(SEND_PATCH, return_value=True):
                    services.decide(request_obj.pk, actor, approve, note="Decisión")
                outcomes.append("ok")
            except services.FourEyesError as exc:
                outcomes.append(exc.code)
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(first, True)),
                   threading.Thread(target=worker, args=(second, False))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        self.assertEqual(sorted(outcomes), ["already_decided", "ok"])
        request_obj.refresh_from_db()
        self.assertIn(request_obj.status, ("approved", "rejected"))
        self.assertEqual(AuditLog.objects.filter(action="FOUR_EYES_DENIED",
                                                 detail__reason="already_decided").count(), 1)
