"""
Sentryx v2 — Pipeline de análisis de contenido de correo.
Modelo: TF-IDF + LinearSVC para detección y clasificación por tipo.
Detecta: spear, whaling, BEC, clone, vishing, smishing, spam genérico.
MITRE ATT&CK: T1566.001 – T1566.004

CORREGIDO: _detect_type() ahora retorna el tipo correcto en modo heurístico.
El clasificador entrenado se usa si existe; si no, la heurística por señales.
"""
import re
import html
from pathlib import Path
from typing import Optional
import joblib
import numpy as np

MODEL_PATH = Path(__file__).parent.parent / "models" / "trained"

# Tipos de phishing — clases del clasificador
PHISHING_TYPES = [
    "spear", "whaling", "bec", "clone",
    "vishing", "smishing", "generic", "legitimate"
]

# Palabras clave por tipo
TYPE_KEYWORDS = {
    "spear": [
        "estimado", "dear", "según nuestra conversación", "as discussed",
        "tu solicitud", "your request", "adjunto el", "attached please find",
        "según lo conversado", "como acordamos",
    ],
    "whaling": [
        "ceo", "director", "gerente", "presidente", "transferencia urgente",
        "urgent wire transfer", "confidencial", "confidential", "no informes",
        "do not discuss", "aprobación inmediata", "immediate approval",
        "operación confidencial", "solo para directivos",
    ],
    "bec": [
        "cambio de cuenta bancaria", "bank account change", "nueva cuenta",
        "new account number", "actualiza los datos de pago", "update payment",
        "proveedor", "vendor", "factura pendiente", "outstanding invoice",
        "datos bancarios", "transferencia de", "cuenta davivienda", "cuenta bancolombia",
    ],
    "clone": [
        "reenviamos", "we resend", "correo anterior", "previous email",
        "link actualizado", "updated link", "nuevo enlace", "new link",
        "hemos actualizado", "we have updated", "el enlace expiró",
    ],
    "vishing": [
        "llama ahora", "call now", "llama al", "call us at",
        "número de soporte", "support number", "habla con un agente",
        "speak to an agent", "no respondas", "do not reply",
        "llame ahora", "llame al", "línea de seguridad",
    ],
    "smishing": [
        "responde sms", "reply sms", "envía whatsapp", "whatsapp us",
        "envíanos un mensaje", "send a message", "código por sms", "sms code",
        "mensaje de whatsapp", "whatsapp al", "envía un mensaje de",
        "número de cédula", "últimos 4 dígitos",
    ],
    "generic": [
        "haz clic aquí", "click here", "haz click", "verify your account",
        "verifica tu cuenta", "login now", "ingresa ahora", "actualiza tu contraseña",
        "update your password", "your account has been", "tu cuenta ha sido",
        "ganar", "winner", "premio", "you have won", "ganador",
        "sorteo", "seleccionado", "reclamar", "gastos administrativos",
    ],
}

# Señales de urgencia transversales
URGENCY_SIGNALS = [
    "urgente", "urgent", "inmediato", "immediately", "ahora mismo",
    "right now", "dentro de 24 horas", "within 24 hours",
    "tu cuenta será suspendida", "your account will be suspended",
    "acción requerida", "action required", "atención inmediata",
    "tiempo límite", "antes de", "expira hoy",
]


def clean_html(raw: str) -> str:
    """Extrae texto plano de HTML de correo."""
    raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.DOTALL | re.I)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    return re.sub(r"\s+", " ", raw).strip()


def extract_content_features(subject: str, body: str) -> dict:
    """Extrae features de contenido del correo para el modelo."""
    body_clean = clean_html(body).lower()
    subject_lc = subject.lower()
    full_text  = subject_lc + " " + body_clean

    # Conteo de señales por tipo
    type_scores = {}
    for ptype, keywords in TYPE_KEYWORDS.items():
        type_scores[ptype] = sum(1 for kw in keywords if kw in full_text)

    # URLs en el cuerpo
    urls   = re.findall(r"https?://[^\s\"'<>]+", body_clean)
    phones = re.findall(r"\+?\d[\d\s\-()]{7,}\d", body_clean)

    features = {
        "body_length":      len(body_clean),
        "subject_length":   len(subject_lc),
        "body_word_count":  len(body_clean.split()),
        "url_count":        len(urls),
        "has_url":          int(len(urls) > 0),
        "has_multiple_urls":int(len(urls) > 3),
        "phone_count":      len(phones),
        "has_phone":        int(len(phones) > 0),
        "urgency_count":    sum(1 for s in URGENCY_SIGNALS if s in full_text),
        "has_urgency":      int(any(s in full_text for s in URGENCY_SIGNALS)),
        "signals_spear":    type_scores["spear"],
        "signals_whaling":  type_scores["whaling"],
        "signals_bec":      type_scores["bec"],
        "signals_clone":    type_scores["clone"],
        "signals_vishing":  type_scores["vishing"],
        "signals_smishing": type_scores["smishing"],
        "signals_generic":  type_scores["generic"],
        "has_html":         int("<html" in body.lower() or "<div" in body.lower()),
        "exclamation_count":body_clean.count("!"),
        "question_count":   body_clean.count("?"),
        "has_spanish":      int(any(w in full_text for w in ["haz clic", "verifica", "cuenta", "contraseña", "urgente"])),
        "has_english":      int(any(w in full_text for w in ["click here", "verify", "account", "password", "urgent"])),
    }

    return features


FEATURE_ORDER = [
    "body_length", "subject_length", "body_word_count",
    "url_count", "has_url", "has_multiple_urls",
    "phone_count", "has_phone",
    "urgency_count", "has_urgency",
    "signals_spear", "signals_whaling", "signals_bec",
    "signals_clone", "signals_vishing", "signals_smishing", "signals_generic",
    "has_html", "exclamation_count", "question_count",
    "has_spanish", "has_english",
]


def features_to_array(features: dict) -> np.ndarray:
    return np.array([[features[f] for f in FEATURE_ORDER]])


class ContentPipeline:
    """
    Pipeline de contenido — TF-IDF + LinearSVC.
    Si no hay modelo entrenado, usa heurística por señales de palabras clave.
    """

    def __init__(self):
        self.model      = None
        self.vectorizer = None
        self.classifier = None
        self.version    = "heuristic"
        self._load()

    def _load(self):
        model_path = MODEL_PATH / "content_svm_v1.joblib"
        clf_path   = MODEL_PATH / "type_classifier_v1.joblib"

        if model_path.exists():
            try:
                pipeline        = joblib.load(model_path)
                self.model      = pipeline
                self.version    = "svm_v1"
            except Exception as e:
                print(f"[WARN] No se pudo cargar content_svm_v1.joblib: {e}")

        if clf_path.exists():
            try:
                self.classifier = joblib.load(clf_path)
            except Exception as e:
                print(f"[WARN] No se pudo cargar type_classifier_v1.joblib: {e}")

    @property
    def is_loaded(self) -> bool:
        return self.model is not None

    def predict(self, subject: str, body: str) -> dict:
        features   = extract_content_features(subject, body)
        body_clean = clean_html(body).lower()
        full_text  = subject.lower() + " " + body_clean

        # Score de phishing (binario)
        if self.model is not None:
            try:
                proba = self.model.predict_proba([full_text])[0][1]
                score = float(min(max(proba * 100, 0), 100))
            except Exception:
                score = self._heuristic_score(features)
        else:
            score = self._heuristic_score(features)

        # Tipo de phishing
        phishing_type = self._detect_type(features, full_text)

        return {
            "score":         round(score, 2),
            "phishing_type": phishing_type,
            "features":      features,
        }

    def _detect_type(self, features: dict, full_text: str = "") -> str:
        """
        Determina el tipo de phishing.
        Usa el clasificador entrenado si existe; si no, heurística por señales.
        """
        # Con modelo entrenado
        if self.classifier is not None and full_text:
            try:
                return self.classifier.predict([full_text])[0]
            except Exception:
                pass

        # Heurística: tipo con más señales detectadas
        signals = {
            "whaling":  features["signals_whaling"],
            "bec":      features["signals_bec"],
            "vishing":  features["signals_vishing"],
            "smishing": features["signals_smishing"],
            "clone":    features["signals_clone"],
            "spear":    features["signals_spear"],
            "generic":  features["signals_generic"],
        }

        # Desempate: prioridad por peligrosidad
        priority = ["whaling", "bec", "vishing", "smishing", "spear", "clone", "generic"]
        max_score = max(signals.values())

        if max_score == 0:
            return "generic"  # Si hay score de phishing pero sin señal específica → genérico

        # Entre los empatados, tomar el de mayor prioridad
        for ptype in priority:
            if signals[ptype] == max_score:
                return ptype

        return "generic"

    def _heuristic_score(self, f: dict) -> float:
        """Score heurístico cuando no hay modelo entrenado."""
        score = 0.0
        score += min(f["signals_generic"]  * 12, 40)
        score += min(f["signals_whaling"]  * 15, 30)
        score += min(f["signals_bec"]      * 15, 30)
        score += min(f["signals_vishing"]  * 15, 25)
        score += min(f["signals_smishing"] * 15, 25)
        score += min(f["signals_spear"]    * 10, 20)
        score += min(f["signals_clone"]    * 10, 20)
        score += min(f["urgency_count"]    * 8,  24)
        if f["has_multiple_urls"]: score += 10
        if f["has_phone"]:         score += 12
        return min(score, 100.0)
