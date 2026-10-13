"""
Sentryx v2 — Ensemble de detección de phishing por correo.
Combina los tres pipelines con pesos configurables:
    - Encabezados (HeadersPipeline): 35%
    - Contenido   (ContentPipeline): 40%
    - URLs        (URLsPipeline):    25%

Score final: 0–100. Clasificación: legitimate | suspicious | phishing | critical
MITRE ATT&CK: T1566.001 – T1566.004
"""
from decouple import config
from pipelines.email_headers import HeadersPipeline
from pipelines.email_content import ContentPipeline
from pipelines.email_urls    import URLsPipeline

# Umbrales (configurables desde .env)
THRESHOLD_SUSPICIOUS = config("ML_THRESHOLD_SUSPICIOUS", default=40, cast=int)
THRESHOLD_PHISHING   = config("ML_THRESHOLD_PHISHING",   default=70, cast=int)
THRESHOLD_CRITICAL   = config("ML_THRESHOLD_CRITICAL",   default=85, cast=int)

# Pesos del ensemble
W_HEADERS = config("ML_WEIGHT_HEADERS", default=0.35, cast=float)
W_CONTENT = config("ML_WEIGHT_CONTENT", default=0.40, cast=float)
W_URLS    = config("ML_WEIGHT_URLS",    default=0.25, cast=float)

# Mapeo tipo de phishing → sub-técnica MITRE ATT&CK (Enterprise v14):
#   T1566.001 Spearphishing Attachment   T1566.002 Spearphishing Link
#   T1566.003 Spearphishing via Service  T1566.004 Spearphishing Voice
# ATT&CK no tiene sub-técnica para SMS ni una específica para BEC. Si se cambia
# este mapa, actualizar también la tabla del README y el manual de pruebas.
MITRE_MAP = {
    "spear":    "T1566.001",
    "whaling":  "T1566.001",
    "bec":      "T1566.002",
    "clone":    "T1566.001",
    "vishing":  "T1566.004",   # pide llamar a un número: Spearphishing Voice
    "smishing": "T1566.003",   # lleva la conversación a SMS/WhatsApp: via Service
    "generic":  "T1566.001",
    "unknown":  "T1566",
}


class EmailEnsemble:
    """
    Pipeline unificado de análisis de correos de phishing.
    Recibe un correo completo (encabezados + cuerpo) y retorna
    el análisis completo con score, tipo y features por capa.
    """

    def __init__(self):
        self.headers_pipe = HeadersPipeline()
        self.content_pipe = ContentPipeline()
        self.urls_pipe    = URLsPipeline()

    @property
    def models_status(self) -> dict:
        return {
            "headers": self.headers_pipe.is_loaded,
            "content": self.content_pipe.is_loaded,
            "urls":    self.urls_pipe.is_loaded,
        }

    def predict(self, email: dict) -> dict:
        """
        Analiza un correo completo.

        Args:
            email: {
                "headers": {
                    "from": "...", "subject": "...",
                    "authentication-results": "...", ...
                },
                "body_text": "Texto plano del cuerpo",
                "body_html": "<html>...</html>",
            }

        Returns:
            {
                "risk_score":    float (0–100),
                "classification": str,
                "phishing_type":  str,
                "mitre_technique":str,
                "scores_by_layer":{headers, content, urls},
                "features_by_layer":{...},
                "urls_analyzed":  [...],
                "model_versions": {...},
            }
        """
        headers   = email.get("headers", {})
        body_text = email.get("body_text", "")
        body_html = email.get("body_html", body_text)
        subject   = headers.get("subject", "")

        # ── Predicciones por capa ─────────────────────────
        h_result = self.headers_pipe.predict(headers)
        c_result = self.content_pipe.predict(subject, body_html or body_text)
        u_result = self.urls_pipe.predict(body_html or body_text)

        score_h = h_result["score"]
        score_c = c_result["score"]
        score_u = u_result["score"]

        # ── Score ensemble ponderado ──────────────────────
        final_score = (
            score_h * W_HEADERS +
            score_c * W_CONTENT +
            score_u * W_URLS
        )
        final_score = round(min(final_score, 100.0), 2)

        # ── Clasificación y tipo ──────────────────────────
        classification = self._classify(final_score)
        phishing_type  = c_result.get("phishing_type", "unknown")
        mitre          = MITRE_MAP.get(phishing_type, "T1566")

        return {
            "risk_score":      final_score,
            "classification":  classification,
            "phishing_type":   phishing_type,
            "mitre_technique": mitre,
            "mitre_tactic":    "Initial Access",
            "scores_by_layer": {
                "headers": round(score_h, 2),
                "content": round(score_c, 2),
                "urls":    round(score_u, 2),
            },
            "features_by_layer": {
                "headers": h_result.get("features", {}),
                "content": c_result.get("features", {}),
            },
            "urls_analyzed": u_result.get("urls_analyzed", []),
            "url_count":     u_result.get("url_count", 0),
            "model_versions": {
                "headers": self.headers_pipe.version,
                "content": self.content_pipe.version,
                "urls":    self.urls_pipe.version,
            },
            "weights": {"headers": W_HEADERS, "content": W_CONTENT, "urls": W_URLS},
        }

    def _classify(self, score: float) -> str:
        if score >= THRESHOLD_CRITICAL:   return "critical"
        if score >= THRESHOLD_PHISHING:   return "phishing"
        if score >= THRESHOLD_SUSPICIOUS: return "suspicious"
        return "legitimate"
