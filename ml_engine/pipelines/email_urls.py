"""
Sentryx v2 — Pipeline de análisis de URLs embebidas en correos.
Modelo: Random Forest sobre features de URL.
El score del correo es el peor score entre todas las URLs encontradas.
MITRE ATT&CK: T1566.001 (Spearphishing Link)
"""
import re
from pathlib import Path
from typing import List, Optional
import joblib
import numpy as np

MODEL_PATH = Path(__file__).parent.parent / "models" / "trained"

PHISHING_KEYWORDS = {
    "login", "signin", "verify", "secure", "account", "update", "confirm",
    "banking", "paypal", "amazon", "ebay", "apple", "microsoft", "google",
    "netflix", "password", "credential", "bancolombia", "davivienda", "nequi",
    "bbva", "dian", "hacienda", "colpensiones",
}

SUSPICIOUS_TLDS = {
    ".tk", ".ml", ".ga", ".cf", ".gq", ".xyz", ".top",
    ".work", ".click", ".link", ".online", ".site", ".info",
}

URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.I)


def extract_urls_from_body(html_body: str) -> List[str]:
    """Extrae todas las URLs del cuerpo del correo (texto o HTML)."""
    return URL_PATTERN.findall(html_body)


def extract_url_features(url: str) -> dict:
    """Features de una URL individual."""
    url_lower   = url.strip().lower()
    no_scheme   = url_lower.replace("https://", "").replace("http://", "")
    parts       = no_scheme.split("/", 1)
    domain_part = parts[0]
    path_part   = parts[1] if len(parts) > 1 else ""
    subdomains  = domain_part.split(".")
    tld         = "." + subdomains[-1] if subdomains else ""

    return {
        "url_length":           len(url),
        "domain_length":        len(domain_part),
        "path_length":          len(path_part),
        "num_dots":             url_lower.count("."),
        "num_hyphens":          url_lower.count("-"),
        "num_slashes":          url_lower.count("/"),
        "num_at_signs":         url_lower.count("@"),
        "num_question_marks":   url_lower.count("?"),
        "num_equal_signs":      url_lower.count("="),
        "num_percent":          url_lower.count("%"),
        "num_subdomains":       max(0, len(subdomains) - 2),
        "has_https":            int(url.startswith("https://")),
        "has_ip_address":       int(bool(re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", domain_part))),
        "has_phishing_keyword": int(any(kw in url_lower for kw in PHISHING_KEYWORDS)),
        "num_phishing_keywords":sum(1 for kw in PHISHING_KEYWORDS if kw in url_lower),
        "has_suspicious_tld":   int(tld in SUSPICIOUS_TLDS),
        "domain_too_long":      int(len(domain_part) > 50),
        "digits_in_domain":     sum(1 for c in domain_part if c.isdigit()),
        "hyphens_in_domain":    domain_part.count("-"),
        "has_redirect_param":   int("url=" in path_part or "redirect=" in path_part or "goto=" in path_part),
    }


FEATURE_ORDER = [
    "url_length", "domain_length", "path_length",
    "num_dots", "num_hyphens", "num_slashes", "num_at_signs",
    "num_question_marks", "num_equal_signs", "num_percent",
    "num_subdomains", "has_https", "has_ip_address",
    "has_phishing_keyword", "num_phishing_keywords",
    "has_suspicious_tld", "domain_too_long",
    "digits_in_domain", "hyphens_in_domain", "has_redirect_param",
]


def features_to_array(features: dict) -> np.ndarray:
    return np.array([[features[f] for f in FEATURE_ORDER]])


class URLsPipeline:
    """
    Pipeline de análisis de URLs en correos.
    El score del correo = score de la URL más peligrosa encontrada.
    """

    def __init__(self):
        self.model   = None
        self.version = "untrained"
        self._load()

    def _load(self):
        path = MODEL_PATH / "url_rf_v1.joblib"
        if path.exists():
            self.model   = joblib.load(path)
            self.version = "rf_v1"

    @property
    def is_loaded(self) -> bool:
        return self.model is not None

    def predict(self, body: str) -> dict:
        """
        Extrae URLs del cuerpo y retorna el score más alto encontrado.
        También retorna la lista de URLs analizadas (máximo 10).
        """
        urls = extract_urls_from_body(body)[:10]  # máximo 10 URLs

        if not urls:
            return {"score": 0.0, "url_count": 0, "worst_url_score": 0.0, "urls_analyzed": []}

        url_results = []
        for url in urls:
            features    = extract_url_features(url)
            X           = features_to_array(features)
            if self.model is not None:
                proba   = self.model.predict_proba(X)[0]
                score   = float(proba[1]) * 100
            else:
                score   = self._heuristic(features)

            url_results.append({
                "url_truncated": url[:80],  # truncada por privacidad
                "score": round(score, 2),
                "features": features,
            })

        # El score del correo = peor URL
        worst_score = max(r["score"] for r in url_results)

        return {
            "score":           round(worst_score, 2),
            "url_count":       len(urls),
            "worst_url_score": round(worst_score, 2),
            "urls_analyzed":   url_results,
        }

    def _heuristic(self, f: dict) -> float:
        score = 0.0
        if f["has_ip_address"]:         score += 35
        if not f["has_https"]:          score += 15
        if f["has_phishing_keyword"]:   score += 20
        if f["has_suspicious_tld"]:     score += 20
        if f["num_subdomains"] > 3:     score += 10
        if f["hyphens_in_domain"] > 1:  score += 10
        if f["has_redirect_param"]:     score += 15
        if f["url_length"] > 120:       score += 8
        if f["num_at_signs"] > 0:       score += 20
        return min(score, 100.0)
