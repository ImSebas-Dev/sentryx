"""Pruebas de la respuesta guiada: incidente, permisos, avisos y paquete de denuncia."""
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.alerts.models import Alert
from apps.audit.models import AuditLog
from apps.incidents.models import Incident
from apps.response import report, services
from apps.response.models import EmergencyContact, Playbook, ResponseSession
from tests.utils import make_user

ORG = "Acme SAS"
SEND_PATCH = "apps.response.services.send_notification"
BASE = "/api/v1/response"


def make_alert(owner, **extra):
    fields = dict(severity="HIGH", phishing_type="bec", title="Alerta", risk_score=82.0,
                  mitre_technique="T1566.002", sender_domain="evil.tk",
                  email_body_hash="a" * 64, sender_hash="b" * 64,
                  suspicious_urls=[{"url": "http://evil.tk/pagar.php", "score": 90}])
    fields.update(extra)
    return Alert.objects.create(owner=owner, **fields)


class ResponseCase(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = make_user("ana@acme.co", organization=ORG)
        self.admin = make_user("jefa@acme.co", role="admin", organization=ORG)
        self.outsider = make_user("otro@otra.co", role="admin", organization="Otra SAS")
        self.client.force_authenticate(self.user)
        patcher = patch(SEND_PATCH, return_value=True)
        self.sent = patcher.start()
        self.addCleanup(patcher.stop)

    def start(self, key="password", **extra):
        return self.client.post(f"{BASE}/start/", {"playbook_key": key, **extra}, format="json")


class TestPlaybooks(ResponseCase):

    def test_migration_loads_four_playbooks(self):
        self.assertEqual(sorted(Playbook.objects.values_list("key", flat=True)),
                         ["attachment", "data", "password", "payment"])

    def test_listed_for_any_authenticated_user(self):
        self.client.force_authenticate(make_user("vera@acme.co", role="viewer", organization=ORG))
        resp = self.client.get(f"{BASE}/playbooks/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 4)
        self.assertTrue(all(step["id"] and "critical" in step for step in resp.data[0]["steps"]))

    def test_anonymous_rejected(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f"{BASE}/playbooks/").status_code, 401)

    def test_playbooks_have_no_phone_numbers(self):
        for playbook in Playbook.objects.all():
            for step in playbook.steps:
                self.assertNotRegex(step["detail"], r"\d{7,}")


class TestStart(ResponseCase):

    def test_creates_incident_timeline_and_session(self):
        resp = self.start("payment", answers={"cuando": "hace 10 minutos"})
        self.assertEqual(resp.status_code, 201, resp.data)
        session = ResponseSession.objects.get()
        incident = session.incident
        playbook = Playbook.objects.get(key="payment")
        self.assertIn(playbook.title, incident.title)
        self.assertEqual(incident.severity, playbook.severity)
        self.assertEqual(incident.created_by, self.user)
        self.assertEqual(incident.timeline.first().description, "Respuesta guiada iniciada")
        self.assertEqual(session.answers, {"cuando": "hace 10 minutos"})
        self.assertTrue(AuditLog.objects.filter(action="RESPONSE_STARTED").exists())

    def test_links_alert(self):
        alert = make_alert(self.user)
        resp = self.start(alert_id=str(alert.pk))
        session = ResponseSession.objects.get(pk=resp.data["id"])
        self.assertEqual(session.alert, alert)
        self.assertIn(alert, session.incident.alerts.all())

    def test_notifies_org_admins_only(self):
        self.start()
        recipients = [c.args[0] for c in self.sent.call_args_list]
        self.assertEqual(recipients, [self.admin.email])

    def test_notification_is_only_logged_without_sendgrid(self):
        with override_settings(SENDGRID_API_KEY=""), patch("apps.users.email_service._send") as raw:
            from apps.users.email_service import send_notification
            self.assertFalse(send_notification("x@y.co", "s", "<p>h</p>"))
        raw.assert_not_called()

    def test_unknown_playbook(self):
        self.assertEqual(self.start("nope").status_code, 400)

    def test_cannot_link_foreign_alert(self):
        foreign = make_alert(self.outsider)
        self.assertEqual(self.start(alert_id=str(foreign.pk)).status_code, 404)
        self.assertEqual(Incident.objects.count(), 0)

    def test_analyst_cannot_link_colleague_alert(self):
        colleague = make_user("beto@acme.co", organization=ORG)
        alert = make_alert(colleague)
        self.assertEqual(self.start(alert_id=str(alert.pk)).status_code, 404)

    def test_admin_can_link_org_alert_but_not_other_org(self):
        alert = make_alert(self.user)
        foreign = make_alert(self.outsider)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.start(alert_id=str(alert.pk)).status_code, 201)
        self.assertEqual(self.start(alert_id=str(foreign.pk)).status_code, 404)

    def test_answers_size_is_limited(self):
        self.assertEqual(self.start(answers={"x": "y" * 5000}).status_code, 400)

    def test_incident_list_marks_guided(self):
        self.start()
        Incident.objects.create(title="Manual", severity="LOW", created_by=self.user)
        results = self.client.get("/api/v1/incidents/").data["results"]
        flags = {i["title"].startswith("Respuesta guiada"): i["guided_response"] for i in results}
        self.assertEqual(flags, {True: True, False: False})


class TestSteps(ResponseCase):

    def setUp(self):
        super().setUp()
        self.session = ResponseSession.objects.get(pk=self.start().data["id"])
        self.step_id = self.session.playbook.steps[0]["id"]

    def step(self, step_id=None, **data):
        return self.client.post(f"{BASE}/{self.session.pk}/steps/{step_id or self.step_id}/",
                                data, format="json")

    def test_marks_step_and_adds_timeline(self):
        resp = self.step(done=True, note="Listo")
        self.assertEqual(resp.status_code, 200, resp.data)
        state = resp.data["steps_state"][self.step_id]
        self.assertTrue(state["done"])
        self.assertTrue(state["done_at"])
        self.assertEqual(state["note"], "Listo")
        events = list(self.session.incident.timeline.values_list("description", flat=True))
        self.assertTrue(any(self.session.playbook.steps[0]["title"] in e for e in events))

    def test_unknown_step(self):
        self.assertEqual(self.step("no-existe", done=True).status_code, 404)

    def test_other_user_gets_404(self):
        self.client.force_authenticate(make_user("beto@acme.co", organization=ORG))
        self.assertEqual(self.step(done=True).status_code, 404)

    def test_other_org_admin_gets_404(self):
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.step(done=True).status_code, 404)
        self.assertEqual(self.client.get(f"{BASE}/{self.session.pk}/").status_code, 404)
        self.assertEqual(self.client.get(f"{BASE}/{self.session.pk}/report.pdf").status_code, 404)

    def test_org_admin_can_help(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.step(done=True).status_code, 200)

    def test_complete(self):
        resp = self.client.post(f"{BASE}/{self.session.pk}/complete/")
        self.assertEqual(resp.data["status"], "completed")
        self.assertIsNotNone(resp.data["completed_at"])
        self.assertEqual(self.step(done=True).status_code, 409)
        self.assertTrue(AuditLog.objects.filter(action="RESPONSE_COMPLETED").exists())


class TestReport(ResponseCase):

    def pdf(self, alert=None):
        alert_field = {"alert_id": str(alert.pk)} if alert else {}
        session_id = self.start(**alert_field).data["id"]
        return self.client.get(f"{BASE}/{session_id}/report.pdf")

    def test_generates_pdf_with_ioc_section(self):
        resp = self.pdf(make_alert(self.user))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))
        self.assertIn(b"Indicadores de compromiso", resp.content)
        self.assertIn(b"Pr\\363ximos pasos", resp.content)
        self.assertIn(b"T1566.002", resp.content)
        self.assertIn(b"a" * 64, resp.content)
        self.assertIn(b"asesor legal", resp.content)

    def test_url_is_defanged_in_pdf(self):
        content = self.pdf(make_alert(self.user)).content
        self.assertIn(b"hxxp://evil[.]tk/pagar[.]php", content)
        self.assertNotIn(b"http://evil.tk", content)
        self.assertNotIn(b"evil.tk", content)

    def test_works_without_alert(self):
        resp = self.pdf()
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Indicadores de compromiso", resp.content)

    def test_user_note_cannot_break_the_pdf(self):
        session_id = self.start().data["id"]
        session = ResponseSession.objects.get(pk=session_id)
        step = session.playbook.steps[0]["id"]
        self.client.post(f"{BASE}/{session_id}/steps/{step}/",
                         {"note": "<b>rota <script> & 🛡 </para>"}, format="json")
        resp = self.client.get(f"{BASE}/{session_id}/report.pdf")
        self.assertEqual(resp.status_code, 200)

    def test_accept_pdf_header_does_not_return_406(self):
        session_id = self.start().data["id"]
        resp = self.client.get(f"{BASE}/{session_id}/report.pdf", HTTP_ACCEPT="application/pdf")
        self.assertEqual(resp.status_code, 200)

    def test_download_is_audited(self):
        self.pdf()
        self.assertTrue(AuditLog.objects.filter(action="EXPORT", resource="response.report").exists())

    @override_settings(CAI_VIRTUAL_URL="https://cai.example.gov.co/denuncia")
    def test_uses_configured_cai_url_defanged(self):
        self.assertIn(b"hxxps://cai[.]example[.]gov[.]co/denuncia", self.pdf().content)

    @override_settings(CAI_VIRTUAL_URL="")
    def test_without_cai_url_gives_instructions(self):
        self.assertIn(b"CAI Virtual", self.pdf().content)

    def test_defang(self):
        self.assertEqual(report.defang("http://ejemplo.com"), "hxxp://ejemplo[.]com")
        self.assertEqual(report.defang("HTTPS://a.b/c.php"), "hxxpS://a[.]b/c[.]php")
        self.assertEqual(report.defang("ejemplo.com"), "ejemplo[.]com")


class TestContacts(ResponseCase):
    URL = f"{BASE}/contacts/"

    def test_placeholders_created_without_numbers(self):
        resp = self.client.get(self.URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), len(services.PLACEHOLDER_CONTACTS))
        for contact in resp.data:
            self.assertEqual(contact["phone"], "")
            self.assertTrue(contact["is_placeholder"])

    def test_config_has_warning(self):
        resp = self.client.get(f"{BASE}/config/")
        self.assertIn("Verifica estos números", resp.data["contact_warning"])

    def test_admin_crud_and_user_read_only(self):
        payload = {"name": "Línea banco", "phone": "+57 601 000 0000", "kind": "bank"}
        self.assertEqual(self.client.post(self.URL, payload, format="json").status_code, 403)
        self.client.force_authenticate(self.admin)
        created = self.client.post(self.URL, payload, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        pk = created.data["id"]
        self.assertEqual(EmergencyContact.objects.get(pk=pk).organization, ORG)
        self.assertEqual(self.client.patch(f"{self.URL}{pk}/", {"name": "X"}, format="json").status_code, 200)
        self.assertEqual(self.client.delete(f"{self.URL}{pk}/").status_code, 204)

    def test_isolation(self):
        self.client.force_authenticate(self.admin)
        pk = self.client.post(self.URL, {"name": "A", "phone": "12345", "kind": "bank"},
                              format="json").data["id"]
        self.client.force_authenticate(self.outsider)
        self.assertNotIn(pk, [c["id"] for c in self.client.get(self.URL).data])
        self.assertEqual(self.client.delete(f"{self.URL}{pk}/").status_code, 404)

    def test_phone_and_url_are_validated(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(self.URL, {"name": "A", "phone": "javascript:x"},
                                          format="json").status_code, 400)
        self.assertEqual(self.client.post(self.URL, {"name": "A", "url": "javascript:alert(1)"},
                                          format="json").status_code, 400)
