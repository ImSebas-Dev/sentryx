"""Sentryx v2 — Tests del ensemble de phishing por correo."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from pipelines.ensemble import EmailEnsemble


def make_email(headers=None, body_text="", body_html=None):
    return {
        "headers":   headers or {},
        "body_text": body_text,
        "body_html": body_html,
    }

LEGIT_EMAIL = make_email(
    headers={
        "from": "newsletter@amazon.com",
        "subject": "Tu pedido ha sido enviado",
        "authentication-results": "spf=pass dkim=pass dmarc=pass",
    },
    body_text="Tu pedido #12345 fue despachado el día de hoy. Gracias por tu compra."
)

PHISHING_BEC = make_email(
    headers={
        "from": "cfo@empresa-segura.tk",
        "reply-to": "attacker@gmail.com",
        "subject": "URGENTE: Cambio de cuenta bancaria del proveedor",
        "authentication-results": "spf=fail dkim=none dmarc=fail",
    },
    body_text=(
        "Estimado equipo, por favor actualiza los datos de pago a nuestra nueva cuenta bancaria. "
        "Esta es una transferencia urgente confidencial. No informes a nadie. "
        "Haz clic aquí para confirmar: http://192.168.1.1/payment/update "
        "Acción requerida antes de las 24 horas."
    )
)


class TestEnsemblePredict:

    def setup_method(self):
        self.ensemble = EmailEnsemble()
        # Forzar modo heurístico en todos los pipelines
        self.ensemble.headers_pipe.model = None
        self.ensemble.content_pipe.model = None
        self.ensemble.content_pipe.vectorizer = None
        self.ensemble.urls_pipe.model = None

    def test_legitimate_email_classified_low(self):
        result = self.ensemble.predict(LEGIT_EMAIL)
        assert result["risk_score"] < 40
        assert result["classification"] in ("legitimate", "suspicious")

    def test_phishing_bec_high_score(self):
        result = self.ensemble.predict(PHISHING_BEC)
        assert result["risk_score"] >= 50
        assert result["classification"] in ("suspicious", "phishing", "critical")

    def test_bec_type_correctly_identified(self):
        result = self.ensemble.predict(PHISHING_BEC)
        assert result["phishing_type"] in ("bec", "whaling", "generic")

    def test_mitre_technique_present(self):
        result = self.ensemble.predict(PHISHING_BEC)
        assert result["mitre_technique"].startswith("T1566")

    def test_mitre_tactic_is_initial_access(self):
        result = self.ensemble.predict(PHISHING_BEC)
        assert result["mitre_tactic"] == "Initial Access"

    def test_scores_by_layer_present(self):
        result = self.ensemble.predict(LEGIT_EMAIL)
        layers = result["scores_by_layer"]
        assert "headers" in layers
        assert "content" in layers
        assert "urls"    in layers

    def test_all_layer_scores_in_range(self):
        result = self.ensemble.predict(PHISHING_BEC)
        for layer, score in result["scores_by_layer"].items():
            assert 0.0 <= score <= 100.0, f"Score de {layer} fuera de rango: {score}"

    def test_final_score_in_range(self):
        for email in [LEGIT_EMAIL, PHISHING_BEC, make_email()]:
            result = self.ensemble.predict(email)
            assert 0.0 <= result["risk_score"] <= 100.0

    def test_classification_valid_values(self):
        valid = {"legitimate", "suspicious", "phishing", "critical"}
        for email in [LEGIT_EMAIL, PHISHING_BEC]:
            result = self.ensemble.predict(email)
            assert result["classification"] in valid

    def test_result_has_all_required_keys(self):
        result = self.ensemble.predict(LEGIT_EMAIL)
        required = {
            "risk_score", "classification", "phishing_type",
            "mitre_technique", "mitre_tactic", "scores_by_layer",
            "url_count", "urls_analyzed", "model_versions", "weights",
        }
        assert required.issubset(set(result.keys()))

    def test_empty_email_handled(self):
        result = self.ensemble.predict(make_email())
        assert "risk_score" in result
        assert 0.0 <= result["risk_score"] <= 100.0

    def test_weights_sum_to_one(self):
        result = self.ensemble.predict(LEGIT_EMAIL)
        w = result["weights"]
        total = w["headers"] + w["content"] + w["urls"]
        assert abs(total - 1.0) < 0.01

    def test_models_status_reported(self):
        result = self.ensemble.predict(LEGIT_EMAIL)
        mv = result["model_versions"]
        assert "headers" in mv
        assert "content" in mv
        assert "urls"    in mv

    @pytest.mark.slow
    def test_performance_50_emails_under_2_seconds(self):
        import time
        emails = [LEGIT_EMAIL, PHISHING_BEC] * 25
        t0 = time.perf_counter()
        for email in emails:
            self.ensemble.predict(email)
        elapsed = time.perf_counter() - t0
        assert elapsed < 2.0, f"50 correos tardaron {elapsed:.2f}s (límite: 2s)"


class TestClassificationThresholds:

    def setup_method(self):
        self.e = EmailEnsemble()

    def test_below_suspicious_threshold(self):
        assert self.e._classify(39) == "legitimate"

    def test_at_suspicious_threshold(self):
        assert self.e._classify(40) == "suspicious"

    def test_at_phishing_threshold(self):
        assert self.e._classify(70) == "phishing"

    def test_at_critical_threshold(self):
        assert self.e._classify(85) == "critical"

    def test_max_score_is_critical(self):
        assert self.e._classify(100) == "critical"


class TestMitreMapping:
    """Sub-técnicas de MITRE ATT&CK v14 que documenta la tesis para los siete tipos."""

    def test_seven_types_map_to_t1566_subtechniques(self):
        from pipelines.ensemble import MITRE_MAP
        expected = {
            "spear": "T1566.001", "whaling": "T1566.001", "bec": "T1566.002",
            "clone": "T1566.001", "vishing": "T1566.004", "smishing": "T1566.003",
            "generic": "T1566.001",
        }
        assert {k: MITRE_MAP[k] for k in expected} == expected
        assert MITRE_MAP["unknown"] == "T1566"
