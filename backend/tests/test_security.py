"""
Sentryx v2 — Pruebas de las protecciones de seguridad.

Cada clase cubre una protección concreta. Si una prueba falla, no la ajustes
para que pase: lo más probable es que se haya reabierto un hueco.
"""
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.alerts.models import Alert
from apps.audit.models import AuditLog
from apps.audit.utils import client_ip
from apps.incidents.models import Incident
from apps.users.models import ShieldUser, hash_token
from tests.utils import make_user

PASSWORD = "SecurePass123!"
WEB = {"HTTP_X_SENTRYX_CLIENT": "web"}
COOKIE = settings.AUTH_REFRESH_COOKIE_NAME


def _alert(owner, **kw):
    return Alert.objects.create(owner=owner, title=kw.pop("title", "Alerta"),
                                risk_score=80, **kw)


# ── Autenticación y enumeración de cuentas ────────────────
class TestLoginDoesNotLeakAccounts(TestCase):

    def setUp(self):
        self.client = APIClient()

    def test_unverified_account_with_wrong_password_looks_like_any_failure(self):
        make_user("sinverificar@pyme.co", is_email_verified=False)
        resp = self.client.post("/api/v1/auth/token/",
                                {"email": "sinverificar@pyme.co", "password": "incorrecta"})
        self.assertEqual(resp.status_code, 401)
        self.assertNotEqual(resp.data.get("code"), "email_not_verified")

    def test_failed_login_is_audited_without_password(self):
        make_user("ana@pyme.co")
        self.client.post("/api/v1/auth/token/", {"email": "ana@pyme.co", "password": "MiClaveSecreta9"})
        log = AuditLog.objects.get(action=AuditLog.Action.LOGIN_FAILED, detail__event="password_failed")
        self.assertTrue(log.detail["account_exists"])
        self.assertNotIn("MiClaveSecreta9", str(log.detail))
        self.assertNotIn("ana@pyme.co", str(log.detail))  # correo seudonimizado


@patch("apps.users.views.send_notification", return_value=True)
@patch("apps.users.views.send_verification_email", return_value=True)
class TestRegistration(TestCase):

    def setUp(self):
        self.client = APIClient()

    def register(self, email="nueva@pyme.co", password=PASSWORD):
        return self.client.post("/api/v1/auth/register/", {
            "email": email, "password": password, "accepted_terms": True})

    def test_existing_email_gets_same_response_and_no_duplicate(self, _verify, notify):
        make_user("ya@pyme.co")
        resp = self.register("ya@pyme.co")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(ShieldUser.objects.filter(email__iexact="ya@pyme.co").count(), 1)
        notify.assert_called_once()  # se avisa al dueño real de la cuenta

    def test_weak_passwords_are_rejected_by_django_validators(self, *_):
        for weak in ("1234567890", "password123", "nueva@pyme.co"):
            resp = self.register(password=weak)
            self.assertEqual(resp.status_code, 400, weak)
            self.assertIn("password", resp.data)
        self.assertFalse(ShieldUser.objects.filter(email="nueva@pyme.co").exists())

    @override_settings(PASSWORD_HASHERS=[
        "django.contrib.auth.hashers.Argon2PasswordHasher",
        "django.contrib.auth.hashers.PBKDF2PasswordHasher"])
    def test_password_is_stored_hashed_with_argon2(self, *_):
        from config.settings import base
        self.assertEqual(base.PASSWORD_HASHERS[0], "django.contrib.auth.hashers.Argon2PasswordHasher")
        self.register()
        user = ShieldUser.objects.get(email="nueva@pyme.co")
        self.assertTrue(user.password.startswith("argon2$"), user.password[:10])
        self.assertNotIn(PASSWORD, user.password)


# ── Enlaces de recuperación ───────────────────────────────
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class TestPasswordReset(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = make_user("ana@pyme.co")

    def confirm(self, token, new_password="OtraClave-Segura-2026"):
        return self.client.post("/api/v1/auth/password-reset/confirm/", {
            "email": "ana@pyme.co", "token": token, "new_password": new_password})

    def test_token_is_stored_only_as_hash(self):
        token = self.user.rotate_reset_token()
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.password_reset_token, token)
        self.assertEqual(self.user.password_reset_token, hash_token(token))

    def test_reset_really_changes_the_password_and_is_single_use(self):
        token = self.user.rotate_reset_token()
        self.assertEqual(self.confirm(token).status_code, 200)
        self.user.refresh_from_db()
        # Regresión: antes set_password() no se guardaba y la contraseña seguía igual
        self.assertTrue(self.user.check_password("OtraClave-Segura-2026"))
        self.assertEqual(self.confirm(token, "Tercera-Clave-2026").status_code, 400)

    def test_link_expires(self):
        token = self.user.rotate_reset_token()
        ShieldUser.objects.filter(pk=self.user.pk).update(
            password_reset_sent_at=timezone.now() - timedelta(
                minutes=settings.PASSWORD_RESET_TIMEOUT_MINUTES + 1))
        self.assertEqual(self.confirm(token).status_code, 400)

    def test_weak_new_password_is_rejected(self):
        token = self.user.rotate_reset_token()
        resp = self.confirm(token, "1234567890")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("new_password", resp.data)

    def test_reset_revokes_open_sessions(self):
        login = self.client.post("/api/v1/auth/token/", {"email": "ana@pyme.co", "password": PASSWORD})
        refresh = login.data["refresh"]
        token = self.user.rotate_reset_token()
        self.assertEqual(self.confirm(token).status_code, 200)
        resp = self.client.post("/api/v1/auth/token/refresh/", {"refresh": refresh})
        self.assertEqual(resp.status_code, 401)

    @override_settings(AUTH_EMAIL_COOLDOWN_SECONDS=60)
    @patch("apps.users.email_service._send", return_value=True)
    def test_reset_emails_have_cooldown(self, send):
        for _ in range(3):
            self.client.post("/api/v1/auth/password-reset/", {"email": "ana@pyme.co"})
        # La primera petición envía; las siguientes, dentro del minuto, no
        self.assertEqual(send.call_count, 1)

    def test_verification_token_is_single_use_and_hashed(self):
        user = make_user("nuevo@pyme.co", is_email_verified=False)
        token = user.rotate_verification_token()
        user.refresh_from_db()
        self.assertEqual(user.email_verification_token, hash_token(token))
        ok = self.client.post("/api/v1/auth/verify-email/", {"email": "nuevo@pyme.co", "token": token})
        self.assertEqual(ok.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.email_verification_token, "")


# ── Cookie del refresh, CSRF y cierre de sesión ───────────
class TestRefreshCookie(TestCase):

    def setUp(self):
        self.client = APIClient()
        make_user("ana@pyme.co")

    def web_login(self):
        return self.client.post("/api/v1/auth/token/",
                                {"email": "ana@pyme.co", "password": PASSWORD}, **WEB)

    def test_web_login_puts_refresh_in_httponly_strict_cookie(self):
        resp = self.web_login()
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.data)
        self.assertNotIn("refresh", resp.data)  # el JavaScript nunca lo ve
        cookie = resp.cookies[COOKIE]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Strict")
        self.assertEqual(cookie["path"], settings.AUTH_REFRESH_COOKIE_PATH)

    def test_extension_still_receives_refresh_in_body(self):
        resp = self.client.post("/api/v1/auth/token/", {"email": "ana@pyme.co", "password": PASSWORD})
        self.assertIn("refresh", resp.data)
        self.assertNotIn(COOKIE, resp.cookies)

    def test_refresh_with_cookie_requires_web_header(self):
        self.web_login()
        # Sin la cabecera (p. ej. un formulario de otro sitio) la cookie no sirve
        self.assertEqual(self.client.post("/api/v1/auth/token/refresh/").status_code, 401)
        resp = self.client.post("/api/v1/auth/token/refresh/", **WEB)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.data)
        self.assertNotIn("refresh", resp.data)

    def test_rotated_refresh_cannot_be_reused(self):
        old = self.client.post("/api/v1/auth/token/",
                               {"email": "ana@pyme.co", "password": PASSWORD}).data["refresh"]
        self.assertEqual(self.client.post("/api/v1/auth/token/refresh/", {"refresh": old}).status_code, 200)
        self.assertEqual(self.client.post("/api/v1/auth/token/refresh/", {"refresh": old}).status_code, 401)

    def test_logout_revokes_refresh_and_clears_cookie(self):
        self.web_login()
        resp = self.client.post("/api/v1/auth/logout/", **WEB)
        self.assertEqual(resp.status_code, 205)
        self.assertEqual(resp.cookies[COOKIE].value, "")
        self.assertEqual(self.client.post("/api/v1/auth/token/refresh/", **WEB).status_code, 401)

    def test_logout_with_body_token_blacklists_it(self):
        refresh = self.client.post("/api/v1/auth/token/",
                                   {"email": "ana@pyme.co", "password": PASSWORD}).data["refresh"]
        self.client.post("/api/v1/auth/logout/", {"refresh": refresh})
        self.assertEqual(self.client.post("/api/v1/auth/token/refresh/", {"refresh": refresh}).status_code, 401)
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.LOGOUT).exists())


# ── Aislamiento entre empresas ────────────────────────────
class TestTenantIsolation(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin_a = make_user("admin@a.co", role="admin", organization="A")
        self.ana_a   = make_user("ana@a.co", organization="A")
        self.beto_b  = make_user("beto@b.co", organization="B")
        self.alert_b = _alert(self.beto_b, title="De B")
        self.client.force_authenticate(self.admin_a)

    def test_admin_cannot_read_other_company_alert(self):
        self.assertEqual(self.client.get(f"/api/v1/alerts/{self.alert_b.pk}/").status_code, 404)

    def test_user_list_only_shows_own_company(self):
        emails = {u["email"] for u in self.client.get("/api/v1/auth/users/").data["results"]}
        self.assertEqual(emails, {"admin@a.co", "ana@a.co"})

    def test_audit_log_only_shows_own_company(self):
        AuditLog.log(AuditLog.Action.LOGIN, "auth", user=self.beto_b)
        AuditLog.log(AuditLog.Action.LOGIN, "auth", user=self.ana_a)
        names = {e["username"] for e in self.client.get("/api/v1/audit/").data["results"]}
        self.assertIn(self.ana_a.username, names)
        self.assertNotIn(self.beto_b.username, names)

    def test_cannot_assign_alert_or_incident_to_other_company(self):
        own = _alert(self.ana_a)
        resp = self.client.patch(f"/api/v1/alerts/{own.pk}/", {"assigned_to": str(self.beto_b.pk)},
                                 format="json")
        self.assertEqual(resp.status_code, 400)
        resp = self.client.post("/api/v1/incidents/", {
            "title": "x", "severity": "HIGH", "assigned_to": str(self.beto_b.pk)}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Incident.objects.filter(title="x").exists())

    def test_feedback_cannot_link_other_company_alert(self):
        resp = self.client.post("/api/v1/ml/feedback/", {
            "correction_type": "false_positive", "correct_label": 0,
            "alert_id": str(self.alert_b.pk)}, format="json")
        self.assertEqual(resp.status_code, 400)


# ── Validación de entradas en el servidor ─────────────────
class TestServerSideValidation(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = make_user("ana@pyme.co")
        self.client.force_authenticate(self.user)

    def test_bad_alert_filters_return_400_not_500(self):
        for query in ("since=ayer", "campaign=no-es-uuid", "severity=ENORME"):
            self.assertEqual(self.client.get(f"/api/v1/alerts/?{query}").status_code, 400, query)

    def test_feedback_rejects_invalid_values(self):
        resp = self.client.post("/api/v1/ml/feedback/", {
            "correction_type": "cualquier_cosa", "correct_label": 7}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("correction_type", resp.data)
        self.assertIn("correct_label", resp.data)

    def test_analyze_rejects_oversized_body(self):
        resp = self.client.post("/api/v1/alerts/analyze/",
                                {"body_text": "x" * 1_000_001}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_ioc_rejects_multiline_value(self):
        resp = self.client.post("/api/v1/threat-intel/iocs/", {
            "ioc_type": "domain", "value": "malo.co\notro.co", "threat_level": "high"}, format="json")
        self.assertEqual(resp.status_code, 400)


# ── Subida de archivos ────────────────────────────────────
@patch("apps.alerts.views.analyze_email_sync")
class TestUploads(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(make_user("ana@pyme.co"))

    def post(self, files):
        return self.client.post("/api/v1/alerts/analyze/",
                                {"body_text": "Pago pendiente", "attachments": files},
                                format="multipart")

    def test_disallowed_type_is_rejected(self, ml):
        resp = self.post([SimpleUploadedFile("factura.exe", b"MZ")])
        self.assertEqual(resp.status_code, 400)
        ml.assert_not_called()

    @override_settings(PAYMENT_SHIELD_MAX_ATTACHMENT_MB=1)
    def test_oversized_file_is_rejected(self, ml):
        resp = self.post([SimpleUploadedFile("factura.xml", b"<a/>" * 300_000)])
        self.assertEqual(resp.status_code, 400)
        ml.assert_not_called()

    def test_too_many_files_are_rejected(self, ml):
        files = [SimpleUploadedFile(f"f{i}.xml", b"<a/>") for i in range(settings.ANALYZE_MAX_ATTACHMENTS + 1)]
        resp = self.post(files)
        self.assertIn(resp.status_code, (400, 413))
        ml.assert_not_called()


# ── IP real y límite de peticiones ────────────────────────
class TestClientIpAndThrottling(TestCase):

    def test_spoofed_forwarded_for_is_ignored(self):
        request = RequestFactory().get("/", HTTP_X_FORWARDED_FOR="1.1.1.1, 203.0.113.9",
                                       REMOTE_ADDR="172.18.0.5")
        # La primera entrada la escribe el cliente; la última, nginx
        self.assertEqual(client_ip(request), "203.0.113.9")

    def test_login_is_rate_limited(self):
        from rest_framework.throttling import ScopedRateThrottle
        client = APIClient()
        with patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"auth_login": "3/min"}):
            from django.core.cache import cache
            cache.clear()
            codes = [client.post("/api/v1/auth/token/", {"email": "x@y.co", "password": "z"}).status_code
                     for _ in range(4)]
        self.assertEqual(codes[-1], 429)


# ── Panel /admin/ ─────────────────────────────────────────
class TestAdminLoginRequiresMfa(TestCase):

    def setUp(self):
        from apps.users import mfa
        self.staff = make_user("jefe@pyme.co", role="admin", is_staff=True, is_superuser=True)
        mfa.start_setup(self.staff)
        mfa.enable(self.staff)
        self.staff.refresh_from_db()
        self.url = f"/{settings.ADMIN_URL}login/"

    def test_password_alone_is_not_enough(self):
        resp = self.client.post(self.url, {"username": "jefe@pyme.co", "password": PASSWORD})
        self.assertEqual(resp.status_code, 200)  # vuelve al formulario con error
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_valid_totp_lets_staff_in(self):
        import pyotp
        from apps.users import mfa
        code = pyotp.TOTP(mfa.decrypt_secret(self.staff.mfa_secret)).now()
        resp = self.client.post(self.url, {"username": "jefe@pyme.co", "password": PASSWORD,
                                           "otp_code": code})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)


# ── Cabeceras, CORS y respuestas ──────────────────────────
class TestHttpHardening(TestCase):

    def test_security_headers(self):
        resp = self.client.get("/api/v1/health/")
        self.assertEqual(resp["X-Frame-Options"], "DENY")
        self.assertEqual(resp["X-Content-Type-Options"], "nosniff")
        self.assertEqual(resp["Referrer-Policy"], "same-origin")
        self.assertEqual(resp["Cross-Origin-Opener-Policy"], "same-origin")

    def test_cors_rejects_unknown_origin(self):
        resp = self.client.get("/api/v1/health/", HTTP_ORIGIN="https://atacante.example")
        self.assertNotIn("Access-Control-Allow-Origin", resp)

    def test_browsable_api_is_off(self):
        client = APIClient()
        client.force_authenticate(make_user("ana@pyme.co"))
        resp = client.get("/api/v1/auth/me/", HTTP_ACCEPT="text/html")
        self.assertNotIn("text/html", resp.get("Content-Type", ""))

    def test_ml_engine_errors_are_not_echoed(self):
        from apps.alerts.ml_client import MLEngineError
        client = APIClient()
        client.force_authenticate(make_user("ana@pyme.co"))
        with patch("apps.alerts.views.analyze_email_sync",
                   side_effect=MLEngineError("ML Engine retornó 500: http://ml_engine:8001 secreto")):
            resp = client.post("/api/v1/alerts/analyze/", {"body_text": "hola"}, format="json")
        self.assertEqual(resp.status_code, 503)
        self.assertNotIn("ml_engine", str(resp.data))


# ── Settings de producción ────────────────────────────────
class TestProductionSettingsGuard(TestCase):

    def test_known_dev_secrets_are_refused(self):
        import importlib
        env = {"DJANGO_SECRET_KEY": "sentryx-dev-secret-key-2026-cambiar-en-produccion",
               "DJANGO_ALLOWED_HOSTS": "sentryx.example.com"}
        with patch.dict("os.environ", env):
            import config.settings.base as base
            importlib.reload(base)
            try:
                with self.assertRaises(ImproperlyConfigured):
                    import config.settings.production as prod
                    importlib.reload(prod)
            finally:
                importlib.reload(base)
