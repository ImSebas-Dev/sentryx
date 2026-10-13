"""
Sentryx v2 — Pipeline de análisis de encabezados de correo.
Modelo: Random Forest sobre features técnicos del encabezado.
Detecta principalmente: BEC, spear phishing, spoofing de dominio.
MITRE ATT&CK: T1566.001, T1566.002
"""
import re
import hashlib
from pathlib import Path
from typing import Optional
import joblib
import numpy as np

MODEL_PATH = Path(__file__).parent.parent / "models" / "trained"

# Dominios de marcas conocidas frecuentemente suplantadas
KNOWN_BRANDS = {
    "paypal", "amazon", "google", "microsoft", "apple", "netflix",
    "bancolombia", "davivienda", "bbva", "nequi", "rappi", "mercadolibre",
    "facebook", "instagram", "whatsapp", "dhl", "fedex", "correos",
    "hacienda", "dian", "colpensiones",
}

# TLDs comúnmente usados en phishing
SUSPICIOUS_TLDS = {".tk", ".ml", ".ga", ".cf", ".gq", ".xyz", ".top",
                    ".work", ".click", ".link", ".online", ".site"}


def levenshtein(a: str, b: str) -> int:
    """Distancia de edición entre dos strings — detecta typosquatting."""
    if len(a) < len(b):
        return levenshtein(b, a)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1,
                            prev[j] + (ca != cb)))
        prev = curr
    return prev[-1]


def min_brand_distance(domain: str) -> int:
    """Mínima distancia Levenshtein entre el dominio y cualquier marca conocida."""
    domain_clean = domain.lower().split(".")[0]
    return min(levenshtein(domain_clean, brand) for brand in KNOWN_BRANDS)


def extract_header_features(headers: dict) -> dict:
    """
    Extrae features técnicos de los encabezados de un correo.

    Args:
        headers: dict con claves en minúsculas, ej:
            {
              "from": "support@paypa1.com",
              "reply-to": "evil@attacker.com",
              "received": ["hop1", "hop2"],
              "authentication-results": "spf=fail dkim=none dmarc=fail",
              "x-spam-status": "Yes, score=8.2",
              "date": "...",
              "subject": "Urgente: verifica tu cuenta",
            }
    """
    from_addr    = headers.get("from", "").lower()
    reply_to     = headers.get("reply-to", "").lower()
    auth_results = headers.get("authentication-results", "").lower()
    received     = headers.get("received", [])
    raw_subject  = headers.get("subject", "")
    subject      = raw_subject.lower()
    x_mailer     = headers.get("x-mailer", "").lower()
    spam_status  = headers.get("x-spam-status", "").lower()

    # Extraer dominio del remitente
    from_match   = re.search(r"@([\w.\-]+)", from_addr)
    from_domain  = from_match.group(1) if from_match else ""
    tld          = "." + from_domain.split(".")[-1] if from_domain else ""

    reply_match  = re.search(r"@([\w.\-]+)", reply_to)
    reply_domain = reply_match.group(1) if reply_match else ""

    # Extraer spam score si existe
    spam_score_match = re.search(r"score=([\d.]+)", spam_status)
    spam_score = float(spam_score_match.group(1)) if spam_score_match else 0.0

    features = {
        # ── Autenticación ──────────────────────────────────
        "spf_pass":     int("spf=pass"     in auth_results),
        "spf_fail":     int("spf=fail"     in auth_results),
        "spf_none":     int("spf=none"     in auth_results or "spf=" not in auth_results),
        "dkim_pass":    int("dkim=pass"    in auth_results),
        "dkim_fail":    int("dkim=fail"    in auth_results),
        "dkim_none":    int("dkim=none"    in auth_results or "dkim=" not in auth_results),
        "dmarc_pass":   int("dmarc=pass"   in auth_results),
        "dmarc_fail":   int("dmarc=fail"   in auth_results or "dmarc=reject" in auth_results),
        "dmarc_none":   int("dmarc=none"   in auth_results or "dmarc=" not in auth_results),

        # ── Remitente y routing ────────────────────────────
        "reply_to_differs":     int(bool(reply_domain) and reply_domain != from_domain),
        "from_domain_length":   len(from_domain),
        "from_has_numbers":     int(bool(re.search(r"\d", from_domain))),
        "from_has_hyphens":     int("-" in from_domain),
        "from_suspicious_tld":  int(tld in SUSPICIOUS_TLDS),
        "from_subdomain_count": max(0, len(from_domain.split(".")) - 2),
        "received_hop_count":   len(received) if isinstance(received, list) else 1,

        # ── Typosquatting ──────────────────────────────────
        # Distancia 1-3 = suplantación muy probable, 0 = dominio real de la marca
        "min_brand_distance":   min_brand_distance(from_domain) if from_domain else 10,
        "brand_in_subdomain":   int(any(b in from_domain for b in KNOWN_BRANDS)
                                     and from_domain not in KNOWN_BRANDS),

        # ── Contenido del asunto ───────────────────────────
        "subject_has_urgency": int(any(w in subject for w in [
            "urgente", "urgent", "inmediato", "inmediata", "immediately",
            "expira", "expires", "suspendido", "suspended", "bloqueado",
            "verify", "verifica", "confirm", "confirma", "action required",
        ])),
        "subject_has_money":   int(any(w in subject for w in [
            "premio", "prize", "winner", "ganador", "reembolso", "refund",
            "transferencia", "transfer", "pago", "payment", "factura", "invoice",
        ])),
        # Comparar contra el asunto original: "subject" ya está en minúsculas
        "subject_all_caps":    int(raw_subject == raw_subject.upper()
                                   and any(c.isalpha() for c in raw_subject)
                                   and len(raw_subject) > 5),

        # ── Metadata sospechosa ────────────────────────────
        "no_x_mailer":         int(not bool(x_mailer)),
        "spam_score":          min(spam_score, 20.0),   # normalizado a máx 20
    }

    return features


FEATURE_ORDER = [
    "spf_pass", "spf_fail", "spf_none",
    "dkim_pass", "dkim_fail", "dkim_none",
    "dmarc_pass", "dmarc_fail", "dmarc_none",
    "reply_to_differs", "from_domain_length", "from_has_numbers",
    "from_has_hyphens", "from_suspicious_tld", "from_subdomain_count",
    "received_hop_count", "min_brand_distance", "brand_in_subdomain",
    "subject_has_urgency", "subject_has_money", "subject_all_caps",
    "no_x_mailer", "spam_score",
]


def features_to_array(features: dict) -> np.ndarray:
    return np.array([[features[f] for f in FEATURE_ORDER]])


class HeadersPipeline:
    """Pipeline de análisis de encabezados — Random Forest."""

    def __init__(self):
        self.model   = None
        self.version = "untrained"
        self._load()

    def _load(self):
        path = MODEL_PATH / "headers_rf_v1.joblib"
        if path.exists():
            self.model   = joblib.load(path)
            self.version = "rf_v1"

    @property
    def is_loaded(self) -> bool:
        return self.model is not None

    def predict(self, headers: dict) -> dict:
        features = extract_header_features(headers)
        X        = features_to_array(features)

        if self.model is not None:
            proba = self.model.predict_proba(X)[0]
            score = float(proba[1]) * 100
        else:
            score = self._heuristic(features)

        return {"score": round(score, 2), "features": features}

    def _heuristic(self, f: dict) -> float:
        """Fallback heurístico antes del primer entrenamiento."""
        score = 0.0
        if f["spf_fail"]:         score += 25
        if f["dkim_fail"]:        score += 20
        if f["dmarc_fail"]:       score += 20
        if f["reply_to_differs"]: score += 15
        d = f["min_brand_distance"]
        if 0 < d <= 2:            score += 20   # typosquatting muy cercano
        elif d == 3:              score += 10
        if f["from_suspicious_tld"]:   score += 10
        if f["subject_has_urgency"]:   score += 8
        if f["brand_in_subdomain"]:    score += 10
        return min(score, 100.0)
