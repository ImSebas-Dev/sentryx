"""Pruebas del hub: registro, k-anonimato, privacidad del feed y antienvenenamiento."""
import json
from datetime import date, datetime, timedelta, timezone

from app import logic
from app.config import settings
from app.db import SessionLocal
from app.models import Node, Report

OPERATOR = ("operator", "operator-test-key")
ACTION = {"X-Operator-Action": "1"}


def h(char):
    return char * 64


def register(client, name="Empresa"):
    resp = client.post("/nodes/register", json={"name": name, "sector": "H", "region": "Cundinamarca"})
    assert resp.status_code == 201, resp.text
    return resp.json()


def approve(client, node_id, established=True):
    resp = client.post(f"/operator/nodes/{node_id}/approve", auth=OPERATOR, headers=ACTION,
                       params={"established": established})
    assert resp.status_code == 200, resp.text


def active_node(client, name="Empresa", established=True):
    reg = register(client, f"Nodo {name}")
    approve(client, reg["node_id"], established)
    claim = client.post("/nodes/claim", json={"node_id": reg["node_id"],
                                              "registration_token": reg["registration_token"]})
    assert claim.status_code == 200, claim.text
    return reg["node_id"], {"X-Node-Key": claim.json()["node_api_key"]}


def indicator(ioc_hash=None, **extra):
    return {"ioc_type": "domain", "ioc_hash": ioc_hash or h("a"), "phishing_type": "bec",
            "mitre_technique": "T1566.002", "severity": "HIGH", "sector": "H",
            "region": "Cundinamarca", "observed_on": str(date.today()), **extra}


def report(client, headers, *items):
    return client.post("/indicators", json={"indicators": list(items)}, headers=headers)


def feed(client, headers, **params):
    resp = client.get("/feed", headers=headers, params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()["indicators"]


class TestRegistration:

    def test_pending_node_has_no_key_until_operator_approves(self, client):
        reg = register(client)
        assert reg["status"] == "pending"
        assert "node_api_key" not in reg
        body = {"node_id": reg["node_id"], "registration_token": reg["registration_token"]}
        assert client.post("/nodes/claim", json=body).status_code == 409
        approve(client, reg["node_id"])
        assert client.post("/nodes/claim", json=body).status_code == 200

    def test_key_is_delivered_only_once(self, client):
        reg = register(client)
        approve(client, reg["node_id"])
        body = {"node_id": reg["node_id"], "registration_token": reg["registration_token"]}
        assert client.post("/nodes/claim", json=body).status_code == 200
        assert client.post("/nodes/claim", json=body).status_code == 401

    def test_wrong_registration_token(self, client):
        reg = register(client)
        approve(client, reg["node_id"])
        body = {"node_id": reg["node_id"], "registration_token": "x"}
        assert client.post("/nodes/claim", json=body).status_code == 401

    def test_only_hash_of_key_is_stored(self, client):
        node_id, headers = active_node(client)
        with SessionLocal() as db:
            node = db.get(Node, node_id)
            assert node.key_hash == logic.hash_secret(headers["X-Node-Key"])
            assert node.key_hash != headers["X-Node-Key"]
            assert node.registration_hash is None

    def test_invalid_sector_or_region(self, client):
        assert client.post("/nodes/register", json={"name": "A1", "sector": "Z",
                                                    "region": "Cundinamarca"}).status_code == 422
        assert client.post("/nodes/register", json={"name": "A1", "sector": "H",
                                                    "region": "Marte"}).status_code == 422

    def test_pending_registrations_are_limited(self, client):
        settings.max_pending_nodes = 1
        register(client)
        resp = client.post("/nodes/register", json={"name": "B1", "sector": "H",
                                                    "region": "Cundinamarca"})
        assert resp.status_code == 429


class TestKAnonymity:

    def test_below_k_is_not_published(self, client):
        _, a = active_node(client, "A")
        assert report(client, a, indicator()).status_code == 200
        assert feed(client, a) == []

    def test_at_k_is_published_with_aggregates(self, client):
        _, a = active_node(client, "A")
        _, b = active_node(client, "B")
        report(client, a, indicator(sector="H", region="Cundinamarca"))
        report(client, b, indicator(sector="C", region="Antioquia"))
        items = feed(client, a)
        assert len(items) == 1
        item = items[0]
        assert item["company_count"] == 2
        assert item["sectors"] == ["C", "H"]
        assert item["regions"] == ["Antioquia", "Cundinamarca"]
        assert item["first_seen"] == str(date.today())

    def test_k_is_configurable(self, client):
        settings.k_anonymity = 3
        _, a = active_node(client, "A")
        _, b = active_node(client, "B")
        report(client, a, indicator())
        report(client, b, indicator())
        assert feed(client, a) == []
        _, c = active_node(client, "C")
        report(client, c, indicator())
        assert feed(client, a)[0]["company_count"] == 3

    def test_same_node_repeating_does_not_reach_k(self, client):
        _, a = active_node(client, "A")
        for _ in range(5):
            report(client, a, indicator())
        assert feed(client, a) == []

    def test_feed_never_exposes_node_identity(self, client):
        id_a, a = active_node(client, "Empresa Secreta A")
        id_b, b = active_node(client, "Empresa Secreta B")
        report(client, a, indicator())
        report(client, b, indicator())
        resp = client.get("/feed", headers=a)
        raw = resp.text
        for secret in (id_a, id_b, "Empresa Secreta", a["X-Node-Key"], b["X-Node-Key"]):
            assert secret not in raw
        assert set(json.loads(raw)["indicators"][0]) == {
            "ioc_hash", "ioc_type", "company_count", "sectors", "regions",
            "phishing_type", "mitre_technique", "first_seen", "last_seen"}

    def test_since_filter(self, client):
        _, a = active_node(client, "A")
        _, b = active_node(client, "B")
        report(client, a, indicator())
        report(client, b, indicator())
        assert feed(client, a, since=str(date.today()))
        assert feed(client, a, since=str(date.today() + timedelta(days=1))) == []


class TestPoisoning:

    def test_new_node_counts_as_half(self, client):
        _, a = active_node(client, "A", established=False)
        _, b = active_node(client, "B", established=False)
        report(client, a, indicator())
        report(client, b, indicator())
        # Dos nodos nuevos suman 1.0: no alcanzan K=2
        assert feed(client, a) == []
        _, c = active_node(client, "C", established=True)
        report(client, c, indicator())
        assert feed(client, a)[0]["company_count"] == 3

    def test_node_older_than_probation_counts_full(self, client):
        node = Node(name="x", sector="H", region="Meta", status="active",
                    approved_at=datetime.now(timezone.utc) - timedelta(days=8))
        assert logic.node_weight(node) == 1.0
        node.approved_at = datetime.now(timezone.utc) - timedelta(days=6)
        assert logic.node_weight(node) == 0.5

    def test_unconfirmed_reports_lower_reputation(self):
        old = date.today() - timedelta(days=10)
        reports = [Report(node_id="spam", ioc_hash=f"{i:064d}", first_observed=old) for i in range(50)]
        reports += [Report(node_id="good", ioc_hash="x" * 64, first_observed=old),
                    Report(node_id="other", ioc_hash="x" * 64, first_observed=old)]
        reputations = logic.compute_reputations(reports)
        assert reputations["spam"] < logic.LOW_REPUTATION
        assert reputations["good"] == 1.0
        node = Node(name="x", sector="H", region="Meta", established=True)
        assert logic.node_weight(node, reputations["spam"]) < 1.0

    def test_recent_reports_do_not_lower_reputation(self):
        recent = date.today()
        reports = [Report(node_id="n", ioc_hash=f"{i:064d}", first_observed=recent) for i in range(50)]
        assert logic.compute_reputations(reports) == {}

    def test_suspended_node_is_rejected_and_stops_counting(self, client):
        id_a, a = active_node(client, "A")
        _, b = active_node(client, "B")
        report(client, a, indicator())
        report(client, b, indicator())
        assert feed(client, b)
        resp = client.post(f"/operator/nodes/{id_a}/suspend", auth=OPERATOR, headers=ACTION)
        assert resp.status_code == 200
        assert report(client, a, indicator(h("b"))).status_code == 403
        assert client.get("/feed", headers=a).status_code == 403
        assert feed(client, b) == []


class TestLimitsAndValidation:

    def test_daily_limit_rejects_whole_batch(self, client):
        settings.daily_limit = 2
        _, a = active_node(client)
        assert report(client, a, indicator(h("a")), indicator(h("b"))).status_code == 200
        assert report(client, a, indicator(h("c"))).status_code == 429
        with SessionLocal() as db:
            assert db.query(Report).count() == 2

    def test_requires_valid_key(self, client):
        assert client.get("/feed").status_code == 401
        assert client.get("/feed", headers={"X-Node-Key": "mala"}).status_code == 401
        assert report(client, {"X-Node-Key": "mala"}, indicator()).status_code == 401

    def test_schema_rejects_extra_fields_like_subject(self, client):
        _, a = active_node(client)
        for field in ("subject", "sender", "organization"):
            assert report(client, a, indicator(**{field: "dato"})).status_code == 422

    def test_schema_validation(self, client):
        _, a = active_node(client)
        bad = [dict(ioc_hash="corto"), dict(ioc_hash="G" * 64), dict(ioc_type="ip"),
               dict(sector="Z"), dict(region="Marte"), dict(mitre_technique="T9999"),
               dict(observed_on=str(date.today() + timedelta(days=5))),
               dict(observed_on=str(date.today() - timedelta(days=60)))]
        for fields in bad:
            assert report(client, a, indicator(**fields)).status_code == 422, fields

    def test_batch_size_limit(self, client):
        _, a = active_node(client)
        assert report(client, a, *[indicator(f"{i:064x}") for i in range(501)]).status_code == 422


class TestDeletion:

    def test_delete_removes_only_own_reports(self, client):
        _, a = active_node(client, "A")
        _, b = active_node(client, "B")
        report(client, a, indicator())
        report(client, b, indicator())
        resp = client.delete("/nodes/me/indicators", headers=a)
        assert resp.json() == {"deleted": 1}
        assert feed(client, b) == []
        with SessionLocal() as db:
            assert db.query(Report).count() == 1

    def test_suspended_node_can_still_delete(self, client):
        id_a, a = active_node(client, "A")
        report(client, a, indicator())
        client.post(f"/operator/nodes/{id_a}/suspend", auth=OPERATOR, headers=ACTION)
        assert client.delete("/nodes/me/indicators", headers=a).status_code == 200


class TestOperator:

    def test_requires_credentials(self, client):
        assert client.get("/operator").status_code == 401
        assert client.get("/operator/nodes", auth=("operator", "mala")).status_code == 401

    def test_panel_and_metrics(self, client):
        active_node(client, "A")
        panel = client.get("/operator", auth=OPERATOR)
        assert panel.status_code == 200
        assert "textContent" in panel.text
        assert client.get("/operator/metrics", auth=OPERATOR).json()["nodes"] == {"active": 1}

    def test_action_needs_header_to_block_csrf(self, client):
        reg = register(client)
        resp = client.post(f"/operator/nodes/{reg['node_id']}/approve", auth=OPERATOR)
        assert resp.status_code == 403

    def test_panel_closed_without_operator_key(self, client):
        original = settings.operator_key
        settings.operator_key = ""
        try:
            assert client.get("/operator", auth=OPERATOR).status_code == 503
        finally:
            settings.operator_key = original

    def test_node_name_is_visible_only_to_operator(self, client):
        active_node(client, "visible al operador")
        assert "visible al operador" in client.get("/operator/nodes", auth=OPERATOR).text

    def test_docs_are_closed(self, client):
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404

    def test_health(self, client):
        assert client.get("/health").json()["status"] == "ok"
