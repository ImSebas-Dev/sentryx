"""Sentryx v2 — Tests del pipeline de contenido (TF-IDF + SVM, modo heurístico)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from pipelines.email_content import (
    extract_content_features, clean_html, ContentPipeline
)


class TestCleanHTML:

    def test_strips_html_tags(self):
        raw = "<p>Haz <b>clic</b> aquí</p>"
        assert "<p>" not in clean_html(raw)
        assert "Haz" in clean_html(raw)

    def test_removes_script_tags(self):
        raw = "<script>alert('xss')</script>Texto limpio"
        assert "alert" not in clean_html(raw)
        assert "Texto limpio" in clean_html(raw)

    def test_decodes_html_entities(self):
        raw = "Cuenta &amp; seguridad"
        assert "&amp;" not in clean_html(raw)
        assert "Cuenta & seguridad" in clean_html(raw)

    def test_normalizes_whitespace(self):
        raw = "hola   mundo\n\ntexto"
        result = clean_html(raw)
        assert "  " not in result


class TestContentFeatureExtraction:

    def test_url_count_detected(self):
        body = "Haz clic en http://evil.com y también en https://otro.tk"
        f = extract_content_features("asunto", body)
        assert f["url_count"] == 2
        assert f["has_url"] == 1

    def test_phone_detected(self):
        body = "Llama al +57 300 1234567 para soporte"
        f = extract_content_features("soporte", body)
        assert f["has_phone"] == 1
        assert f["phone_count"] >= 1

    def test_urgency_detected(self):
        f = extract_content_features(
            "Acción requerida",
            "Tu cuenta será suspendida en 24 horas. Verifica urgente."
        )
        assert f["has_urgency"] == 1
        assert f["urgency_count"] >= 1

    def test_no_urgency_in_normal_email(self):
        f = extract_content_features(
            "Newsletter semanal",
            "Aquí están las novedades de la semana."
        )
        assert f["has_urgency"] == 0

    def test_bec_signals_detected(self):
        f = extract_content_features(
            "Cambio de cuenta bancaria",
            "Por favor actualiza los datos de pago a nuestra nueva cuenta bancaria."
        )
        assert f["signals_bec"] >= 1

    def test_whaling_signals_detected(self):
        f = extract_content_features(
            "Confidencial — Director General",
            "Estimado CEO, necesito una transferencia urgente confidencial. No informes a nadie."
        )
        assert f["signals_whaling"] >= 2

    def test_vishing_signals_detected(self):
        f = extract_content_features(
            "Llama ahora",
            "No respondas este correo. Llama al número de soporte +1-800-123-4567."
        )
        assert f["signals_vishing"] >= 1
        assert f["has_phone"] == 1

    def test_all_features_present(self):
        f = extract_content_features("test", "test body")
        required = {
            "body_length", "subject_length", "body_word_count",
            "url_count", "has_url", "has_multiple_urls",
            "phone_count", "has_phone",
            "urgency_count", "has_urgency",
            "signals_spear", "signals_whaling", "signals_bec",
            "signals_clone", "signals_vishing", "signals_smishing", "signals_generic",
            "has_html", "exclamation_count", "question_count",
            "has_spanish", "has_english",
        }
        assert required.issubset(set(f.keys()))

    def test_all_features_numeric(self):
        f = extract_content_features("asunto", "cuerpo del correo")
        for k, v in f.items():
            assert isinstance(v, (int, float)), f"Feature '{k}' no es numérica"


class TestContentPipelineHeuristic:

    def setup_method(self):
        self.pipe = ContentPipeline()
        self.pipe.model      = None
        self.pipe.vectorizer = None

    def test_legitimate_email_low_score(self):
        result = self.pipe.predict(
            "Newsletter mensual",
            "Aquí están las noticias de este mes. Esperamos que sean de su interés."
        )
        assert result["score"] < 40

    def test_generic_phishing_high_score(self):
        result = self.pipe.predict(
            "URGENTE: Haz clic aquí para verificar tu cuenta",
            "Haz clic aquí ahora. Tu cuenta será suspendida. Verifica tu contraseña urgente. "
            "Click here to update your password. Action required."
        )
        assert result["score"] >= 40

    def test_bec_type_detected(self):
        result = self.pipe.predict(
            "Cambio de datos bancarios",
            "Por favor actualiza los datos de pago a nuestra nueva cuenta bancaria del proveedor."
        )
        assert result["phishing_type"] == "bec"

    def test_whaling_type_detected(self):
        result = self.pipe.predict(
            "Confidencial CEO",
            "Estimado CEO, transferencia urgente confidencial. No informes. Aprobación inmediata requerida."
        )
        assert result["phishing_type"] == "whaling"

    def test_vishing_type_detected(self):
        result = self.pipe.predict(
            "Llama ahora",
            "No respondas. Llama al número de soporte +57 300 1234567. Habla con un agente ahora."
        )
        assert result["phishing_type"] == "vishing"

    def test_score_in_valid_range(self):
        cases = [
            ("normal", "texto normal sin nada sospechoso"),
            ("URGENTE", "haz clic aquí click here verify account suspendida"),
            ("", ""),
        ]
        for subject, body in cases:
            r = self.pipe.predict(subject, body)
            assert 0.0 <= r["score"] <= 100.0

    def test_result_has_required_keys(self):
        r = self.pipe.predict("test", "body")
        assert "score" in r
        assert "phishing_type" in r
        assert "features" in r
