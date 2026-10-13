"""
Pruebas de la verificación en dos pasos (TOTP) y del login en dos pasos.
"""
import time
from unittest.mock import patch

import pyotp
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.users import mfa
from tests.utils import make_user

PASSWORD = "SecurePass123!"
TOKEN_URL  = "/api/v1/auth/token/"
VERIFY_URL = "/api/v1/auth/mfa/verify/"


def enable_mfa(user):
    """Activar 2FA directamente y devolver (secreto, códigos de recuperación)."""
    secret = mfa.start_setup(user)["secret"]
    codes = mfa.enable(user)
    return secret, codes


class MFATestCase(TestCase):
    def setUp(self):
        # La caché (locmem) guarda throttles, jti y el último intervalo TOTP
        # usado: limpiarla para que cada prueba empiece de cero.
        cache.clear()
        self.client = APIClient()

    def login(self, email, password=PASSWORD):
        return self.client.post(TOKEN_URL, {"email": email, "password": password})


class TestTwoStepLogin(MFATestCase):

    def setUp(self):
        super().setUp()
        self.user = make_user("ana@sentryx.local")
        self.secret, self.codes = enable_mfa(self.user)

    def mfa_token(self):
        resp = self.login("ana@sentryx.local")
        self.assertEqual(resp.status_code, 200)
        return resp.data["mfa_token"]

    def test_login_with_mfa_returns_challenge_not_jwt(self):
        resp = self.login("ana@sentryx.local")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["mfa_required"])
        self.assertIn("mfa_token", resp.data)
        self.assertEqual(resp.data["expires_in"], 300)
        self.assertNotIn("access", resp.data)
        self.assertNotIn("refresh", resp.data)

    def test_wrong_password_does_not_reach_mfa(self):
        resp = self.login("ana@sentryx.local", "incorrecta")
        self.assertEqual(resp.status_code, 401)
        self.assertNotIn("mfa_token", resp.data)

    def test_valid_totp_returns_jwt(self):
        token = self.mfa_token()
        resp = self.client.post(VERIFY_URL, {"mfa_token": token,
                                             "code": pyotp.TOTP(self.secret).now()})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)
        # El JWT funciona en un endpoint protegido
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 200)

    def test_previous_window_code_is_accepted(self):
        token = self.mfa_token()
        previous = pyotp.TOTP(self.secret).at(time.time() - 30)
        resp = self.client.post(VERIFY_URL, {"mfa_token": token, "code": previous})
        self.assertEqual(resp.status_code, 200)

    def test_invalid_code(self):
        token = self.mfa_token()
        resp = self.client.post(VERIFY_URL, {"mfa_token": token, "code": "000000"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "mfa_invalid_code")
        self.assertEqual(resp.data["attempts_left"], 4)
        self.assertTrue(AuditLog.objects.filter(
            action=AuditLog.Action.LOGIN_FAILED, resource="mfa",
            detail__event="mfa_verify_failed").exists())

    def test_expired_token(self):
        token = self.mfa_token()
        later = time.time() + 301
        with patch("django.core.signing.time.time", return_value=later):
            resp = self.client.post(VERIFY_URL, {"mfa_token": token,
                                                 "code": pyotp.TOTP(self.secret).now()})
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.data["code"], "mfa_token_expired")

    def test_tampered_token(self):
        token = self.mfa_token()
        resp = self.client.post(VERIFY_URL, {"mfa_token": token[:-2] + "xx",
                                             "code": pyotp.TOTP(self.secret).now()})
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.data["code"], "mfa_token_invalid")

    def test_reused_token(self):
        token = self.mfa_token()
        code = pyotp.TOTP(self.secret).now()
        self.assertEqual(self.client.post(VERIFY_URL, {"mfa_token": token, "code": code}
                                          ).status_code, 200)
        resp = self.client.post(VERIFY_URL, {"mfa_token": token, "code": code})
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.data["code"], "mfa_token_used")

    def test_same_totp_cannot_be_replayed_with_new_token(self):
        code = pyotp.TOTP(self.secret).now()
        first = self.client.post(VERIFY_URL, {"mfa_token": self.mfa_token(), "code": code})
        self.assertEqual(first.status_code, 200)
        second = self.client.post(VERIFY_URL, {"mfa_token": self.mfa_token(), "code": code})
        self.assertEqual(second.status_code, 400)

    def test_recovery_code_works_once(self):
        code = self.codes[0]
        resp = self.client.post(VERIFY_URL, {"mfa_token": self.mfa_token(),
                                             "recovery_code": code})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["recovery_codes_remaining"], 7)
        self.assertTrue(AuditLog.objects.filter(
            resource="mfa", detail__event="mfa_recovery_code_used").exists())

        again = self.client.post(VERIFY_URL, {"mfa_token": self.mfa_token(),
                                              "recovery_code": code})
        self.assertEqual(again.status_code, 400)
        self.assertEqual(again.data["code"], "mfa_invalid_code")

    def test_recovery_code_ignores_case_and_hyphen(self):
        code = self.codes[1].replace("-", "").upper()
        resp = self.client.post(VERIFY_URL, {"mfa_token": self.mfa_token(),
                                             "recovery_code": code})
        self.assertEqual(resp.status_code, 200)

    # Subir el límite de axes para probar solo el límite por mfa_token
    @override_settings(MFA_MAX_ATTEMPTS=5, AXES_FAILURE_LIMIT=50)
    def test_attempt_limit_per_token(self):
        token = self.mfa_token()
        for left in (4, 3, 2, 1):
            resp = self.client.post(VERIFY_URL, {"mfa_token": token, "code": "000000"})
            self.assertEqual(resp.data["attempts_left"], left)
        fifth = self.client.post(VERIFY_URL, {"mfa_token": token, "code": "000000"})
        self.assertEqual(fifth.status_code, 401)
        self.assertEqual(fifth.data["code"], "mfa_too_many_attempts")
        # Ni siquiera el código correcto sirve ya con ese token
        resp = self.client.post(VERIFY_URL, {"mfa_token": token,
                                             "code": pyotp.TOTP(self.secret).now()})
        self.assertEqual(resp.status_code, 401)

    @override_settings(AXES_FAILURE_LIMIT=3)
    def test_mfa_failures_count_for_axes_lockout(self):
        token = self.mfa_token()
        for _ in range(3):
            resp = self.client.post(VERIFY_URL, {"mfa_token": token, "code": "000000"})
        self.assertEqual(resp.status_code, 429)
        # Con la cuenta bloqueada, tampoco se puede volver a entrar con contraseña
        self.assertEqual(self.login("ana@sentryx.local").status_code, 429)

    def test_ip_rate_limit(self):
        token = self.mfa_token()
        statuses = [self.client.post(VERIFY_URL, {"mfa_token": token, "code": "1"}
                                     ).status_code for _ in range(11)]
        self.assertEqual(statuses[-1], 429)

    def test_secret_is_encrypted_at_rest(self):
        self.user.refresh_from_db()
        self.assertNotIn(self.secret, self.user.mfa_secret)
        self.assertEqual(mfa.decrypt_secret(self.user.mfa_secret), self.secret)
        for code in self.codes:
            self.assertNotIn(code, self.user.mfa_recovery_codes)


class TestLoginWithoutMFA(MFATestCase):

    def test_login_without_mfa_is_unchanged(self):
        make_user("sin2fa@sentryx.local")
        resp = self.login("sin2fa@sentryx.local")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.data)
        self.assertNotIn("mfa_required", resp.data)
        self.assertNotIn("mfa_setup_required", resp.data)


class TestMFAManagement(MFATestCase):

    def setUp(self):
        super().setUp()
        self.user = make_user("luis@sentryx.local")
        self.client.force_authenticate(self.user)

    def test_setup_returns_secret_and_qr_without_enabling(self):
        resp = self.client.post("/api/v1/auth/mfa/setup/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["qr_code"].startswith("data:image/png;base64,"))
        self.assertIn("issuer=Sentryx", resp.data["otpauth_url"])
        self.user.refresh_from_db()
        self.assertFalse(self.user.mfa_enabled)

    def test_enable_requires_valid_code(self):
        self.client.post("/api/v1/auth/mfa/setup/")
        resp = self.client.post("/api/v1/auth/mfa/enable/", {"code": "123456"})
        self.assertEqual(resp.status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.mfa_enabled)

    def test_enable_returns_8_recovery_codes_once(self):
        secret = self.client.post("/api/v1/auth/mfa/setup/").data["secret"]
        resp = self.client.post("/api/v1/auth/mfa/enable/",
                                {"code": pyotp.TOTP(secret).now()})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data["recovery_codes"]), 8)
        self.user.refresh_from_db()
        self.assertTrue(self.user.mfa_enabled)
        self.assertIsNotNone(self.user.mfa_enabled_at)
        self.assertTrue(AuditLog.objects.filter(
            resource="mfa", detail__event="mfa_enabled").exists())
        # /me/ informa el estado pero nunca los códigos
        me = self.client.get("/api/v1/auth/me/").data
        self.assertTrue(me["mfa_enabled"])
        self.assertEqual(me["mfa_recovery_codes_remaining"], 8)
        self.assertNotIn("mfa_recovery_codes", me)
        self.assertNotIn("mfa_secret", me)

    def test_disable_requires_password_and_code(self):
        secret, codes = enable_mfa(self.user)
        bad = self.client.post("/api/v1/auth/mfa/disable/",
                               {"password": "mala", "code": codes[0]})
        self.assertEqual(bad.status_code, 400)
        self.user.refresh_from_db()
        # Una contraseña incorrecta no debe gastar el código de recuperación
        self.assertEqual(len(self.user.mfa_recovery_codes), 8)

        ok = self.client.post("/api/v1/auth/mfa/disable/",
                              {"password": PASSWORD, "code": pyotp.TOTP(secret).now()})
        self.assertEqual(ok.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.mfa_enabled)
        self.assertEqual(self.user.mfa_secret, "")
        self.assertTrue(AuditLog.objects.filter(
            resource="mfa", detail__event="mfa_disabled").exists())

    @override_settings(MFA_ENCRYPTION_KEY="")
    def test_not_configured_returns_503(self):
        resp = self.client.post("/api/v1/auth/mfa/setup/")
        self.assertEqual(resp.status_code, 503)


class TestAdminPolicy(MFATestCase):

    def setUp(self):
        super().setUp()
        self.admin = make_user("admin@sentryx.local", role="admin")

    @override_settings(MFA_REQUIRED_FOR_ADMINS=True)
    def test_admin_without_mfa_can_only_set_it_up(self):
        resp = self.login("admin@sentryx.local")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["mfa_setup_required"])
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

        blocked = self.client.get("/api/v1/alerts/")
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.data["code"], "mfa_setup_required")
        self.assertTrue(self.client.get("/api/v1/auth/me/").data["mfa_setup_required"])

        secret = self.client.post("/api/v1/auth/mfa/setup/").data["secret"]
        enabled = self.client.post("/api/v1/auth/mfa/enable/",
                                   {"code": pyotp.TOTP(secret).now()})
        self.assertEqual(enabled.status_code, 200)
        # Recibe tokens sin el claim y ya puede usar el resto de la API
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {enabled.data['access']}")
        self.assertEqual(self.client.get("/api/v1/alerts/").status_code, 200)

    @override_settings(MFA_REQUIRED_FOR_ADMINS=True)
    def test_analyst_not_affected_by_admin_policy(self):
        make_user("analista@sentryx.local")
        resp = self.login("analista@sentryx.local")
        self.assertNotIn("mfa_setup_required", resp.data)

    @override_settings(MFA_REQUIRED_FOR_ADMINS=True)
    def test_admin_cannot_disable_when_required(self):
        secret, _ = enable_mfa(self.admin)
        self.client.force_authenticate(self.admin)
        resp = self.client.post("/api/v1/auth/mfa/disable/",
                                {"password": PASSWORD, "code": pyotp.TOTP(secret).now()})
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_reset_other_user(self):
        user = make_user("perdio@sentryx.local")
        enable_mfa(user)
        self.client.force_authenticate(self.admin)
        resp = self.client.post(f"/api/v1/auth/users/{user.pk}/mfa/reset/")
        self.assertEqual(resp.status_code, 200)
        user.refresh_from_db()
        self.assertFalse(user.mfa_enabled)
        log = AuditLog.objects.get(resource="mfa", detail__event="mfa_reset_by_admin")
        self.assertEqual(log.detail["target_email"], "perdio@sentryx.local")

    def test_non_admin_cannot_reset(self):
        analyst = make_user("ana2@sentryx.local")
        self.client.force_authenticate(analyst)
        resp = self.client.post(f"/api/v1/auth/users/{self.admin.pk}/mfa/reset/")
        self.assertEqual(resp.status_code, 403)
