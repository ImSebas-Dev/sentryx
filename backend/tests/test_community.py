"""Pruebas de la Red de alerta en el nodo: privacidad, opt-in y funcionamiento sin hub."""
import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

import httpx
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.alerts.models import Alert
from apps.audit.models import AuditLog
from apps.community import services
from apps.community.constants import DEPARTMENTS, SECTORS
from apps.community.models import CommunityIndicator, CommunitySettings, OutboxEntry
from apps.community.tasks import community_sync_task
from tests.test_payment_shield import ML_LOW, make_supplier
from tests.utils import make_user

ORG = "Acme SAS"
ML_PATCH = "apps.alerts.views.analyze_email_sync"
HUB = "apps.community.services._hub_request"
BASE = "/api/v1/community"
ML_PHISHING = {
    **ML_LOW, "risk_score": 82.0, "classification": "phishing", "phishing_type": "bec",
    "mitre_technique": "T1566.002",
    "urls_analyzed": [
        {"url_truncated": "http://evil.tk/pay?id=1", "score": 85.0},
        {"url_truncated": "https://aliado.co/inicio", "score": 5.0},
    ],
}


def enable_org(organization=ORG, sector="H", region="Cundinamarca"):
    return CommunitySettings.objects.create(
        organization=organization, enabled=True, sector=sector, region=region)


def indicator(value, company_count=3, **extra):
    today = timezone.localdate()
    fields = dict(ioc_type="domain", company_count=company_count, sectors=["H"],
                  regions=["Cundinamarca"], phishing_type="bec", mitre_technique="T1566.002",
                  first_seen=today, last_seen=today)
    fields.update(extra)
    return CommunityIndicator.objects.create(ioc_hash=services.ioc_hash(value), **fields)


def fake_response(data=None, status=200):
    response = MagicMock(status_code=status)
    response.json.return_value = data or {}
    return response


class TestNormalization(TestCase):

    def test_domain(self):
        self.assertEqual(services.normalize_domain("WWW.Evil.TK."), "evil.tk")
        self.assertEqual(services.normalize_domain("mail.evil.tk"), "mail.evil.tk")

    def test_url_removes_tracking_and_noise(self):
        self.assertEqual(
            services.normalize_url("HTTP://WWW.Evil.tk:80/Pay/?utm_source=x&b=2&a=1&gclid=9#frag"),
            "http://evil.tk/Pay?a=1&b=2")
        self.assertEqual(services.normalize_url("https://evil.tk:8443/"), "https://evil.tk:8443")

    def test_same_url_gives_same_hash_for_all_recipients(self):
        first = services.normalize_url("http://evil.tk/p?utm_campaign=a")
        second = services.normalize_url("http://www.evil.tk/p/?utm_campaign=b&fbclid=z")
        self.assertEqual(services.ioc_hash(first), services.ioc_hash(second))

    def test_hmac_depends_on_network_key(self):
        self.assertEqual(len(services.ioc_hash("evil.tk")), 64)
        self.assertNotEqual(services.ioc_hash("evil.tk", "clave-a"), services.ioc_hash("evil.tk", "clave-b"))
        self.assertNotIn("evil", services.ioc_hash("evil.tk"))

    def test_lists_are_complete(self):
        self.assertEqual(len(DEPARTMENTS), 33)
        self.assertEqual([s[0] for s in SECTORS], list("ABCDEFGHIJKLMNOPQRSTU"))


class CommunityCase(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin = make_user("jefa@acme.co", role="admin", organization=ORG)
        self.analyst = make_user("ana@acme.co", organization=ORG)
        self.client.force_authenticate(self.analyst)

    def analyze(self, sender="x@evil.tk", body="Hola", **extra):
        return self.client.post("/api/v1/alerts/analyze/", {
            "headers": {"from_addr": sender}, "body_text": body, **extra}, format="json")


class TestMatching(CommunityCase):

    @patch(ML_PATCH, return_value=ML_LOW)
    def test_match_elevates_without_touching_score(self, _):
        enable_org()
        indicator("evil.tk", company_count=3)
        resp = self.analyze()
        self.assertEqual(resp.status_code, 201, resp.data)
        alert = Alert.objects.get(pk=resp.data["alert_id"])
        self.assertEqual(alert.risk_score, 12.0)
        self.assertEqual(alert.severity, "HIGH")
        signal = alert.risk_signals["community"]
        self.assertEqual(signal["company_count"], 3)
        self.assertEqual(signal["sectors"], ["H"])
        self.assertEqual(signal["regions"], ["Cundinamarca"])
        self.assertTrue(signal["first_seen"])
        self.assertIn("3 empresas de tu sector", resp.data["community"]["message"])
        self.assertEqual(alert.risk_signals["severity_adjustments"][0]["layer"], "community")

    @patch(ML_PATCH, return_value={**ML_LOW, "risk_score": 45.0, "classification": "suspicious"})
    def test_single_company_only_informs(self, _):
        enable_org()
        indicator("evil.tk", company_count=1)
        resp = self.analyze()
        self.assertEqual(resp.data["severity"], "MEDIUM")
        self.assertEqual(resp.data["community"]["company_count"], 1)

    @patch(ML_PATCH, return_value=ML_LOW)
    def test_single_company_with_low_score_creates_no_alert(self, _):
        enable_org()
        indicator("evil.tk", company_count=1)
        self.assertFalse(self.analyze().data["alert_created"])

    @patch(ML_PATCH, return_value=ML_LOW)
    def test_matches_url_in_body(self, _):
        enable_org()
        indicator(services.normalize_url("https://otro.co/robo"), ioc_type="url")
        resp = self.analyze(sender="x@ok.co", body="Entra a https://www.otro.co/robo/?utm_source=m")
        self.assertIn("community", resp.data)

    @patch(ML_PATCH, return_value=ML_LOW)
    def test_matches_domain_of_url_in_body(self, _):
        enable_org()
        indicator("otro.co")
        resp = self.analyze(sender="x@ok.co", body="Entra a https://otro.co/a")
        self.assertIn("community", resp.data)

    @patch(ML_PATCH, return_value=ML_LOW)
    def test_opt_out_org_gets_no_match(self, _):
        indicator("evil.tk")
        self.assertNotIn("community", self.analyze().data)

    @override_settings(COMMUNITY_NETWORK_KEY="")
    @patch(ML_PATCH, return_value=ML_LOW)
    def test_without_network_key_nothing_breaks(self, _):
        enable_org()
        resp = self.analyze()
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("community", resp.data)

    @patch(ML_PATCH, return_value=ML_LOW)
    def test_free_mail_domains_never_match(self, _):
        enable_org()
        indicator("gmail.com")
        self.assertNotIn("community", self.analyze(sender="alguien@gmail.com").data)

    @patch(ML_PATCH, return_value=ML_LOW)
    def test_analysis_never_calls_the_hub(self, _):
        enable_org()
        with patch(HUB) as hub:
            self.analyze()
        hub.assert_not_called()

    @patch(ML_PATCH, return_value=ML_LOW)
    def test_layer_failure_does_not_break_analysis(self, _):
        with patch("apps.community.services.match_email", side_effect=RuntimeError("boom")):
            self.assertEqual(self.analyze().status_code, 200)


class TestSharing(CommunityCase):

    @patch(ML_PATCH, return_value=ML_PHISHING)
    def test_nothing_recorded_or_sent_without_opt_in(self, _):
        self.analyze()
        self.assertEqual(OutboxEntry.objects.count(), 0)
        with patch(HUB) as hub:
            self.assertIn("skipped", services.sync())
        hub.assert_not_called()

    @patch(ML_PATCH, return_value=ML_PHISHING)
    def test_payload_has_only_allowed_fields(self, _):
        enable_org()
        self.analyze(sender="Gerente General <gerente@evil.tk>",
                     body="Secreto del cuerpo http://evil.tk/pay?id=1",
                     headers={"from_addr": "gerente@evil.tk", "subject": "Asunto secreto",
                              "to_addr": "ana@acme.co"})
        with patch(HUB, return_value=fake_response()) as hub:
            self.assertEqual(services.push_indicators(), 2)
        body = hub.call_args.kwargs["json"]
        self.assertEqual({"ioc_type", "ioc_hash", "phishing_type", "mitre_technique", "severity",
                          "sector", "region", "observed_on"}, set(body["indicators"][0]))
        raw = json.dumps(body)
        for private in ("Secreto", "Asunto", "gerente", "evil.tk", ORG, "ana@acme", "Gerente"):
            self.assertNotIn(private, raw)
        self.assertRegex(body["indicators"][0]["observed_on"], r"^\d{4}-\d{2}-\d{2}$")

    @patch(ML_PATCH, return_value=ML_PHISHING)
    def test_low_score_urls_are_not_shared(self, _):
        enable_org()
        self.analyze(body="http://evil.tk/pay?id=1 https://aliado.co/inicio")
        hashes = set(OutboxEntry.objects.values_list("ioc_hash", flat=True))
        self.assertNotIn(services.ioc_hash(services.normalize_url("https://aliado.co/inicio")), hashes)
        self.assertIn(services.ioc_hash(services.normalize_url("http://evil.tk/pay?id=1")), hashes)

    @patch(ML_PATCH, return_value=ML_PHISHING)
    def test_uses_full_url_not_truncated(self, _):
        enable_org()
        long_url = "http://evil.tk/" + "a" * 100
        result = {**ML_PHISHING, "urls_analyzed": [{"url_truncated": long_url[:80], "score": 90.0}]}
        with patch(ML_PATCH, return_value=result):
            self.analyze(body=f"Entra a {long_url}")
        expected = services.ioc_hash(services.normalize_url(long_url))
        self.assertTrue(OutboxEntry.objects.filter(ioc_hash=expected).exists())

    @patch(ML_PATCH, return_value=ML_PHISHING)
    def test_free_mail_and_own_suppliers_are_not_shared(self, _):
        enable_org()
        make_supplier()
        self.analyze(sender="x@gmail.com")
        self.analyze(sender="x@proveedor.co")
        self.assertFalse(OutboxEntry.objects.filter(ioc_hash=services.ioc_hash("gmail.com")).exists())
        self.assertFalse(OutboxEntry.objects.filter(ioc_hash=services.ioc_hash("proveedor.co")).exists())

    @patch(ML_PATCH, return_value={**ML_LOW, "risk_score": 50.0, "classification": "suspicious"})
    def test_medium_score_waits_for_analyst_confirmation(self, _):
        enable_org()
        alert_id = self.analyze().data["alert_id"]
        with patch(HUB, return_value=fake_response()) as hub:
            self.assertEqual(services.push_indicators(), 0)
            hub.assert_not_called()
            Alert.objects.filter(pk=alert_id).update(status="resolved")
            self.assertEqual(services.push_indicators(), 1)

    @patch(ML_PATCH, return_value=ML_PHISHING)
    def test_false_positive_is_never_shared(self, _):
        enable_org()
        alert_id = self.analyze().data["alert_id"]
        Alert.objects.filter(pk=alert_id).update(status="false_pos")
        with patch(HUB, return_value=fake_response()) as hub:
            self.assertEqual(services.push_indicators(), 0)
        hub.assert_not_called()

    @patch(ML_PATCH, return_value=ML_PHISHING)
    def test_not_sent_twice(self, _):
        enable_org()
        self.analyze()
        with patch(HUB, return_value=fake_response()) as hub:
            services.push_indicators()
            calls = hub.call_count
            services.push_indicators()
        self.assertEqual(hub.call_count, calls)

    @patch(ML_PATCH, return_value=ML_PHISHING)
    def test_alerts_before_consent_are_not_shared(self, _):
        self.analyze()
        enable_org()
        with patch(HUB, return_value=fake_response()) as hub:
            self.assertEqual(services.push_indicators(), 0)
        hub.assert_not_called()


FEED = {"indicators": [{
    "ioc_hash": "a" * 64, "ioc_type": "domain", "company_count": 4, "sectors": ["H"],
    "regions": ["Meta"], "phishing_type": "bec", "mitre_technique": "T1566.002",
    "first_seen": "2026-11-01", "last_seen": "2026-11-03",
}]}


@override_settings(COMMUNITY_HUB_URL="http://hub:8100", COMMUNITY_NODE_API_KEY="key")
class TestSync(CommunityCase):

    def test_pull_updates_copy_and_removes_revoked(self):
        indicator("viejo.tk")
        with patch(HUB, return_value=fake_response(FEED)):
            self.assertEqual(services.pull_feed(), 1)
        self.assertEqual(list(CommunityIndicator.objects.values_list("ioc_hash", flat=True)), ["a" * 64])
        self.assertEqual(CommunityIndicator.objects.get().company_count, 4)

    def test_sync_updates_status(self):
        community = enable_org()
        with patch(HUB, return_value=fake_response(FEED)):
            result = community_sync_task()
        self.assertEqual(result["pulled"], 1)
        community.refresh_from_db()
        self.assertEqual(community.node_status, "active")
        self.assertIsNotNone(community.last_sync_at)

    def test_unreachable_hub_does_not_raise(self):
        community = enable_org()
        with patch("apps.community.services.httpx.request", side_effect=httpx.ConnectError("x")):
            result = community_sync_task()
        self.assertIn("error", result)
        community.refresh_from_db()
        self.assertEqual(community.node_status, "unreachable")

    def test_rejected_node_is_marked_suspended(self):
        community = enable_org()
        with patch("apps.community.services.httpx.request", return_value=MagicMock(status_code=403)):
            community_sync_task()
        community.refresh_from_db()
        self.assertEqual(community.node_status, "suspended")

    @patch(ML_PATCH, return_value=ML_PHISHING)
    def test_entries_stay_unsent_if_hub_fails(self, _):
        enable_org()
        self.analyze()
        with patch("apps.community.services.httpx.request", side_effect=httpx.ConnectError("x")):
            community_sync_task()
        self.assertTrue(OutboxEntry.objects.filter(sent_at__isnull=True).exists())

    def test_sends_node_key_in_header(self):
        with patch("apps.community.services.httpx.request",
                   return_value=fake_response(FEED)) as request:
            services.pull_feed()
        self.assertEqual(request.call_args.kwargs["headers"], {"X-Node-Key": "key"})

    def test_beat_task_is_registered(self):
        from django_celery_beat.models import PeriodicTask
        task = PeriodicTask.objects.get(name="community_sync")
        self.assertEqual(task.task, "community.sync")
        self.assertEqual((task.interval.every, task.interval.period), (15, "minutes"))


class TestWithoutHub(CommunityCase):

    @override_settings(COMMUNITY_HUB_URL="", COMMUNITY_NODE_API_KEY="")
    def test_sync_without_config_warns_and_skips(self):
        community = enable_org()
        with patch(HUB) as hub:
            self.assertEqual(community_sync_task(), {"skipped": "sin configuración"})
        hub.assert_not_called()
        community.refresh_from_db()
        self.assertEqual(community.node_status, "not_configured")

    @override_settings(COMMUNITY_HUB_URL="")
    @patch(ML_PATCH, return_value=ML_LOW)
    def test_analysis_works_without_hub(self, _):
        enable_org()
        self.assertEqual(self.analyze().status_code, 200)


class TestConsent(CommunityCase):
    ENABLE = {"accept_consent": True, "sector": "H", "region": "Cundinamarca"}

    def test_off_by_default(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get(f"{BASE}/settings/")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["enabled"])
        self.assertIn("Qué nunca se comparte", resp.data["consent_text"])
        self.assertEqual(len(resp.data["region_options"]), 33)

    def test_only_admin(self):
        for path in ("enable/", "disable/", "sync/"):
            self.assertEqual(self.client.post(f"{BASE}/{path}", self.ENABLE, format="json").status_code, 403)
        self.assertEqual(self.client.get(f"{BASE}/settings/").status_code, 403)

    def test_requires_explicit_consent(self):
        self.client.force_authenticate(self.admin)
        for body in ({**self.ENABLE, "accept_consent": False}, {"sector": "H", "region": "Meta"}):
            self.assertEqual(self.client.post(f"{BASE}/enable/", body, format="json").status_code, 400)
        self.assertFalse(CommunitySettings.objects.filter(enabled=True).exists())

    def test_enable_records_who_when_and_audits(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(f"{BASE}/enable/", self.ENABLE, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        community = CommunitySettings.objects.get(organization=ORG)
        self.assertTrue(community.enabled)
        self.assertEqual(community.consent_accepted_by, self.admin)
        self.assertIsNotNone(community.consent_accepted_at)
        self.assertTrue(AuditLog.objects.filter(action="COMMUNITY_OPT_IN").exists())

    def test_invalid_sector_or_region(self):
        self.client.force_authenticate(self.admin)
        for bad in ({"sector": "Z"}, {"region": "Marte"}):
            resp = self.client.post(f"{BASE}/enable/", {**self.ENABLE, **bad}, format="json")
            self.assertEqual(resp.status_code, 400)

    def test_user_without_org(self):
        self.client.force_authenticate(make_user("solo@x.co", role="admin"))
        self.assertEqual(self.client.get(f"{BASE}/settings/").status_code, 400)

    def test_settings_are_per_organization(self):
        self.client.force_authenticate(self.admin)
        self.client.post(f"{BASE}/enable/", self.ENABLE, format="json")
        self.client.force_authenticate(make_user("otra@otra.co", role="admin", organization="Otra"))
        self.assertFalse(self.client.get(f"{BASE}/settings/").data["enabled"])

    def _shared_entry(self, organization=ORG, sent=True):
        owner = self.analyst if organization == ORG else make_user(
            "b@otra.co", organization=organization)
        alert = Alert.objects.create(owner=owner, severity="HIGH", title="A", risk_score=80)
        return OutboxEntry.objects.create(organization=organization, alert=alert, ioc_type="domain",
                                          ioc_hash="f" * 64, sent_at=timezone.now() if sent else None)

    @override_settings(COMMUNITY_HUB_URL="http://hub", COMMUNITY_NODE_API_KEY="key")
    def test_disable_stops_sending_and_asks_hub_to_delete(self):
        enable_org()
        self._shared_entry()
        self.client.force_authenticate(self.admin)
        with patch(HUB, return_value=fake_response()) as hub:
            resp = self.client.post(f"{BASE}/disable/")
        self.assertEqual(resp.status_code, 200)
        hub.assert_called_once_with("DELETE", "/nodes/me/indicators")
        self.assertFalse(resp.data["enabled"])
        self.assertFalse(resp.data["deletion_pending"])
        self.assertEqual(OutboxEntry.objects.count(), 0)
        self.assertTrue(AuditLog.objects.filter(action="COMMUNITY_OPT_OUT").exists())

    @override_settings(COMMUNITY_HUB_URL="http://hub", COMMUNITY_NODE_API_KEY="key")
    def test_disable_with_hub_down_retries_later(self):
        community = enable_org()
        self._shared_entry()
        self.client.force_authenticate(self.admin)
        with patch("apps.community.services.httpx.request", side_effect=httpx.ConnectError("x")):
            resp = self.client.post(f"{BASE}/disable/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["deletion_pending"])
        with patch(HUB, return_value=fake_response()) as hub:
            community_sync_task()
        hub.assert_called_once_with("DELETE", "/nodes/me/indicators")
        community.refresh_from_db()
        self.assertFalse(community.deletion_pending)

    @override_settings(COMMUNITY_HUB_URL="http://hub", COMMUNITY_NODE_API_KEY="key")
    def test_revocation_resends_other_org_of_same_install(self):
        enable_org()
        enable_org("Otra SAS")
        self._shared_entry()
        other = self._shared_entry("Otra SAS")
        with patch(HUB, return_value=fake_response()):
            services.disable(CommunitySettings.objects.get(organization=ORG))
        other.refresh_from_db()
        self.assertIsNone(other.sent_at)

    def test_disable_never_shared_does_not_call_hub(self):
        enable_org()
        self.client.force_authenticate(self.admin)
        with patch(HUB) as hub:
            self.client.post(f"{BASE}/disable/")
        hub.assert_not_called()

    @override_settings(COMMUNITY_HUB_URL="http://hub", COMMUNITY_NODE_API_KEY="key")
    def test_disable_clears_local_copy_if_nobody_else_uses_it(self):
        enable_org()
        indicator("evil.tk")
        with patch(HUB, return_value=fake_response()):
            services.disable(CommunitySettings.objects.get(organization=ORG))
        self.assertEqual(CommunityIndicator.objects.count(), 0)


class TestSummary(CommunityCase):
    URL = f"{BASE}/summary/"

    def test_disabled(self):
        self.assertEqual(self.client.get(self.URL).data["enabled"], False)

    @patch(ML_PATCH, return_value=ML_LOW)
    def test_counts_campaigns_of_sector_and_region_and_matches(self, _):
        enable_org()
        indicator("evil.tk")
        indicator("otra.tk", sectors=["C"])
        indicator("lejos.tk", regions=["Meta"])
        indicator("vieja.tk", last_seen=timezone.localdate() - timedelta(days=5))
        self.analyze()
        data = self.client.get(self.URL).data
        self.assertEqual(data["active_campaigns"], 1)
        self.assertEqual(data["matches"], 1)
