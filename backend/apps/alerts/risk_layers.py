"""
Sentryx v2 — Capas de negocio que corren después del ensemble.

Reglas para quien agregue una capa nueva aquí:
  - No modifiques risk_score, score_* ni los pesos o umbrales: el puntaje del
    ensemble debe seguir siendo reproducible a partir de los modelos.
  - Deja el detalle en Alert.risk_signals["<capa>"] y explica cada ajuste de
    severidad en risk_signals["severity_adjustments"].
  - Atrapa los errores de cada capa: si una capa falla, el análisis sigue.
"""
import logging

from apps.alerts.models import Alert
from apps.payment_shield import services as payment_shield
from apps.users.organization import org_of

logger = logging.getLogger(__name__)

SEVERITY_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
BEC_TECHNIQUE = "T1566.002"


def severity_at_least(severity: str, minimum: str) -> bool:
    return SEVERITY_RANK.get(severity, 0) >= SEVERITY_RANK.get(minimum, 0)


def elevate_severity(alert, minimum: str, layer: str, reason: str) -> bool:
    """Sube la severidad al mínimo indicado y registra por qué. Nunca la baja."""
    if severity_at_least(alert.severity, minimum):
        return False
    alert.risk_signals.setdefault("severity_adjustments", []).append(
        {"layer": layer, "from": alert.severity, "to": minimum, "reason": reason})
    alert.severity = minimum
    return True


class RiskLayers:
    """Reúne lo que cada capa calculó para un correo antes de crear la alerta."""

    def __init__(self, email_payload, attachments, attachment_names, user):
        self.email_payload = email_payload
        self.attachments = list(attachments or [])
        self.attachment_names = list(attachment_names or [])
        self.user = user
        self.organization = org_of(user)
        self.shield = None
        self.response = {}

    def evaluate(self):
        headers = self.email_payload.get("headers", {})
        try:
            self.shield = payment_shield.evaluate_email(
                self.organization, headers.get("from", ""),
                self.email_payload.get("body_text", ""),
                self.email_payload.get("body_html", ""), self.attachments,
            )
        except Exception:
            logger.exception("[RiskLayers] Falló el Escudo de pagos")
        return self

    @property
    def force_alert(self) -> bool:
        # Crea la alerta aunque el score sea bajo: un BEC bien escrito engaña al
        # modelo de contenido, y sin alerta no habría dónde elevar la severidad.
        return bool(self.shield and self.shield.is_risky)

    def adjust_ml_result(self, ml_result: dict) -> dict:
        """Copia del resultado con el tipo de ataque corregido; el score no se toca."""
        if self.shield and self.shield.is_risky:
            return {**ml_result, "phishing_type": "bec", "mitre_technique": BEC_TECHNIQUE}
        return ml_result

    def apply(self, alert) -> dict:
        """Persiste lo evaluado y devuelve los campos extra de la respuesta del análisis."""
        check = None
        try:
            if self.shield and self.shield.should_persist:
                check = payment_shield.persist_check(self.shield, alert, self.user)
                self.response["payment_shield"] = payment_shield.check_summary(check)
        except Exception:
            logger.exception("[RiskLayers] No se pudo guardar el Escudo de pagos")

        if alert is not None:
            if check is not None:
                alert.risk_signals["payment_shield"] = self.response["payment_shield"]
            if check is not None and check.is_risky:
                elevate_severity(alert, Alert.Severity.HIGH, "payment_shield",
                                 payment_shield.VERDICT_MESSAGES[check.verdict])
            alert.save(update_fields=["risk_signals", "severity"])
            self.response["severity"] = alert.severity
        return self.response
