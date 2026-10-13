"""Sentryx v2 — Tests del pipeline de encabezados (heurístico)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from pipelines.email_headers import extract_header_features, HeadersPipeline, min_brand_distance


# ── Fixtures ──────────────────────────────────────────────
def legit_headers():
    return {
        "from": "newsletter@amazon.com",
        "subject": "Tu pedido ha sido enviado",
        "authentication-results": "spf=pass dkim=pass dmarc=pass",
        "received": ["hop1", "hop2"],
    }

def phishing_headers():
    return {
        "from": "soporte@bancolombia-seguro.tk",
        "reply-to": "attacker@evil.com",
        "subject": "URGENTE: Verifica tu cuenta o será suspendida",
        "authentication-results": "spf=fail dkim=none dmarc=fail",
        "received": ["hop1", "hop2", "hop3", "hop4", "hop5"],
    }


class TestFeatureExtraction:

    def test_spf_pass_detected(self):
        f = extract_header_features({"authentication-results": "spf=pass dkim=pass dmarc=pass"})
        assert f["spf_pass"] == 1
        assert f["spf_fail"] == 0

    def test_spf_fail_detected(self):
        f = extract_header_features({"authentication-results": "spf=fail dkim=none dmarc=fail"})
        assert f["spf_fail"] == 1
        assert f["dmarc_fail"] == 1

    def test_reply_to_differs_from_from(self):
        f = extract_header_features({
            "from": "ceo@company.com",
            "reply-to": "attacker@evil.com",
        })
        assert f["reply_to_differs"] == 1

    def test_reply_to_same_as_from(self):
        f = extract_header_features({
            "from": "user@company.com",
            "reply-to": "other@company.com",
        })
        assert f["reply_to_differs"] == 0

    def test_suspicious_tld_detected(self):
        f = extract_header_features({"from": "support@banco.tk"})
        assert f["from_suspicious_tld"] == 1

    def test_normal_tld_not_suspicious(self):
        f = extract_header_features({"from": "info@amazon.com"})
        assert f["from_suspicious_tld"] == 0

    def test_urgency_in_subject(self):
        f = extract_header_features({"subject": "URGENTE: Verifica tu cuenta"})
        assert f["subject_has_urgency"] == 1

    def test_no_urgency_in_normal_subject(self):
        f = extract_header_features({"subject": "Tu pedido ha llegado"})
        assert f["subject_has_urgency"] == 0

    def test_all_caps_subject(self):
        f = extract_header_features({"subject": "ACCION REQUERIDA AHORA"})
        assert f["subject_all_caps"] == 1

    def test_hop_count(self):
        f = extract_header_features({"received": ["h1", "h2", "h3", "h4", "h5"]})
        assert f["received_hop_count"] == 5

    def test_all_features_present(self):
        f = extract_header_features(legit_headers())
        required = {
            "spf_pass", "spf_fail", "spf_none",
            "dkim_pass", "dkim_fail", "dkim_none",
            "dmarc_pass", "dmarc_fail", "dmarc_none",
            "reply_to_differs", "from_domain_length", "from_has_numbers",
            "from_has_hyphens", "from_suspicious_tld", "from_subdomain_count",
            "received_hop_count", "min_brand_distance", "brand_in_subdomain",
            "subject_has_urgency", "subject_has_money", "subject_all_caps",
            "no_x_mailer", "spam_score",
        }
        assert required.issubset(set(f.keys()))

    def test_all_features_numeric(self):
        f = extract_header_features(phishing_headers())
        for k, v in f.items():
            assert isinstance(v, (int, float)), f"Feature '{k}' no es numérica: {type(v)}"


class TestTyposquatting:

    def test_exact_brand_distance_zero(self):
        # "paypal" está en KNOWN_BRANDS
        assert min_brand_distance("paypal.com") == 0

    def test_typosquat_distance_one(self):
        # paypa1 tiene distancia 1 respecto a paypal
        dist = min_brand_distance("paypa1.com")
        assert dist <= 2

    def test_unrelated_domain_high_distance(self):
        dist = min_brand_distance("xyzqrstuvwxyz.com")
        assert dist >= 5


class TestHeadersPipelineHeuristic:

    def setup_method(self):
        self.pipe = HeadersPipeline()
        self.pipe.model = None   # forzar heurístico

    def test_legitimate_email_low_score(self):
        result = self.pipe.predict(legit_headers())
        assert result["score"] < 40

    def test_phishing_email_high_score(self):
        result = self.pipe.predict(phishing_headers())
        assert result["score"] >= 60

    def test_score_in_valid_range(self):
        for headers in [legit_headers(), phishing_headers(), {}]:
            result = self.pipe.predict(headers)
            assert 0.0 <= result["score"] <= 100.0

    def test_result_has_required_keys(self):
        result = self.pipe.predict(legit_headers())
        assert "score" in result
        assert "features" in result

    def test_empty_headers_handled(self):
        result = self.pipe.predict({})
        assert "score" in result
        assert 0.0 <= result["score"] <= 100.0
