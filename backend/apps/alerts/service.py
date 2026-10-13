"""
Sentryx v2 — Servicio de creación de alertas con soporte de owner.
Cada alerta queda vinculada al usuario que la generó.
El admin puede ver todas; los demás solo las suyas.
"""
from django.conf import settings
from apps.alerts.models import Alert, PhishingCampaign
from apps.alerts.pseudonymize import (
    pseudonymize_email, pseudonymize_subject, pseudonymize_text,
    extract_domain, safe_truncate_url,
)

TYPE_TITLES = {
    "spear":   "Spear phishing detectado",
    "whaling": "Whaling (phishing a ejecutivo) detectado",
    "bec":     "Business Email Compromise (BEC) detectado",
    "clone":   "Clone phishing detectado",
    "vishing": "Vishing por correo detectado",
    "smishing":"Smishing por correo detectado",
    "generic": "Phishing genérico detectado",
    "unknown": "Correo sospechoso detectado",
}


def _severity_from_score(score: float) -> str:
    t = settings.ML_THRESHOLDS
    if score >= t["critical"]:   return Alert.Severity.CRITICAL
    if score >= t["phishing"]:   return Alert.Severity.HIGH
    if score >= t["suspicious"]: return Alert.Severity.MEDIUM
    return Alert.Severity.LOW


def _normalize_type(raw: str) -> str:
    valid = {"spear","whaling","bec","clone","vishing","smishing","generic","unknown"}
    t = (raw or "unknown").lower().strip()
    return t if t in valid else "generic"


def _should_create_alert(classification: str) -> bool:
    return classification in ("suspicious", "phishing", "critical")


def create_alert_from_ml_result(
    ml_result:     dict,
    email_payload: dict,
    triggered_by:  str  = "api",
    owner=None,                      # ← usuario que disparó el análisis
) -> "Alert | None":
    """
    Crea una alerta vinculada al usuario que la generó (owner).
    Los analistas ven solo sus propias alertas.
    Los admins ven todas.
    """
    if not _should_create_alert(ml_result.get("classification", "legitimate")):
        return None

    headers       = email_payload.get("headers", {})
    score         = float(ml_result.get("risk_score", 0))
    scores        = ml_result.get("scores_by_layer", {})
    phishing_type = _normalize_type(ml_result.get("phishing_type", "unknown"))

    sender_hash   = pseudonymize_email(headers.get("from", ""))
    recipient_hash = pseudonymize_email(headers.get("to", ""))
    subject_hash  = pseudonymize_subject(headers.get("subject", ""))
    body_hash     = pseudonymize_text(
        email_payload.get("body_text") or email_payload.get("body_html", "")
    )
    sender_domain = extract_domain(headers.get("from", ""))

    suspicious_urls = [
        {"url": safe_truncate_url(u.get("url_truncated", "")), "score": u.get("score", 0)}
        for u in ml_result.get("urls_analyzed", [])
        if u.get("score", 0) >= 40
    ][:10]

    description = (
        f"Tipo: {phishing_type} | Score: {score:.0f}/100 | "
        f"Dominio: {sender_domain or 'desconocido'} | "
        f"URLs sospechosas: {len(suspicious_urls)}"
    )

    alert = Alert.objects.create(
        owner          = owner,                           # ← NUEVO
        severity       = _severity_from_score(score),
        phishing_type  = phishing_type,
        status         = Alert.Status.NEW,
        title          = TYPE_TITLES.get(phishing_type, "Correo sospechoso"),
        description    = description,
        risk_score     = score,
        score_headers  = float(scores.get("headers", 0)),
        score_content  = float(scores.get("content", 0)),
        score_urls     = float(scores.get("urls",    0)),
        sender_hash    = sender_hash,
        recipient_hash = recipient_hash,
        subject_hash   = subject_hash,
        sender_domain  = sender_domain,
        email_body_hash= body_hash,
        has_attachments= False,
        url_count      = ml_result.get("url_count", 0),
        ml_features    = ml_result.get("features_by_layer", {}),
        suspicious_urls= suspicious_urls,
        mitre_tactic   = ml_result.get("mitre_tactic", "Initial Access"),
        mitre_technique= ml_result.get("mitre_technique", "T1566"),
    )

    _assign_or_create_campaign(alert, sender_domain, phishing_type, owner)
    return alert


def _assign_or_create_campaign(alert, sender_domain, phishing_type, owner):
    if not sender_domain:
        return
    from django.utils import timezone
    from datetime import timedelta

    window_start = timezone.now() - timedelta(hours=1)

    # La campaña se detecta solo dentro del universo del mismo usuario
    # (o globalmente para el admin)
    recent_qs = Alert.objects.filter(
        sender_domain=sender_domain,
        detected_at__gte=window_start,
    ).exclude(pk=alert.pk)

    if owner and not owner.is_admin:
        recent_qs = recent_qs.filter(owner=owner)

    if recent_qs.count() < 2:
        return

    campaign, _ = PhishingCampaign.objects.get_or_create(
        indicator=sender_domain,
        is_active=True,
        owner=owner,
        defaults={
            "name":            f"Campaña desde {sender_domain}",
            "description":     f"Campaña de {phishing_type} detectada automáticamente.",
            "mitre_technique": alert.mitre_technique,
        },
    )

    # Filtrar por dueño igual que recent_qs: sin esto, las alertas de otros
    # usuarios con el mismo dominio terminaban dentro de esta campaña.
    to_group = Alert.objects.filter(
        sender_domain=sender_domain,
        detected_at__gte=window_start,
        campaign__isnull=True,
    )
    if owner and not owner.is_admin:
        to_group = to_group.filter(owner=owner)
    to_group.update(campaign=campaign)

    alert.campaign = campaign
    alert.save(update_fields=["campaign"])

    PhishingCampaign.objects.filter(pk=campaign.pk).update(
        alert_count=Alert.objects.filter(campaign=campaign).count()
    )
