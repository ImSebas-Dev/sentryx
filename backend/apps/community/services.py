"""
Sentryx v2 — Lógica del nodo en la Red de alerta.

Reglas que protegen la privacidad y la disponibilidad; no las relajes:
  - Nada sale sin opt-in: revisa CommunitySettings.enabled antes de enviar.
  - Al hub solo le llegan los campos de _report_for(). No agregues otros.
  - El análisis de un correo nunca llama al hub: solo consulta la copia local.
  - Sin hub o con el hub caído se registra un aviso y todo lo demás sigue igual.
"""
import hashlib
import hmac
import logging
import re
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.alerts.models import Alert
from apps.community.constants import (
    CONSENT_VERSION, EXCLUDED_DOMAINS, TRACKING_PARAMS, TRACKING_PREFIXES,
)
from apps.community.models import CommunityIndicator, CommunitySettings, OutboxEntry
from apps.payment_shield.models import Supplier
from apps.payment_shield.services import domain_from_header

logger = logging.getLogger(__name__)

URL_RE = re.compile(r"https?://[^\s\"'<>)\]]+", re.IGNORECASE)
HUB_TIMEOUT = 10.0
MIN_SHARE_SCORE = 70
MIN_URL_SCORE = 40
ELEVATE_FROM_COMPANIES = 2
FEED_WINDOW_DAYS = 30
BATCH_SIZE = 500


# ── Normalización y huella ────────────────────────────────
def normalize_domain(domain: str) -> str:
    domain = (domain or "").strip().lower().rstrip(".")
    return domain[4:] if domain.startswith("www.") else domain


def normalize_url(url: str) -> str:
    """Quita lo que cambia entre destinatarios: www, puerto por defecto y rastreo."""
    parts = urlsplit((url or "").strip())
    scheme = parts.scheme.lower()
    host = normalize_domain(parts.hostname or "")
    port = parts.port
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        host = f"{host}:{port}"
    query = sorted(
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS and not k.lower().startswith(TRACKING_PREFIXES)
    )
    path = parts.path.rstrip("/")
    return urlunsplit((scheme, host, path, urlencode(query), ""))


def ioc_hash(value: str, key: str | None = None) -> str:
    """HMAC con la clave común de la red: debe dar lo mismo en todos los nodos."""
    key = key if key is not None else settings.COMMUNITY_NETWORK_KEY
    return hmac.new(key.encode(), value.encode(), hashlib.sha256).hexdigest()


def network_ready() -> bool:
    return bool(settings.COMMUNITY_NETWORK_KEY)


def hub_ready() -> bool:
    return bool(settings.COMMUNITY_HUB_URL and settings.COMMUNITY_NODE_API_KEY)


def settings_for(organization: str) -> CommunitySettings | None:
    if not organization:
        return None
    return CommunitySettings.objects.get_or_create(organization=organization)[0]


def is_enabled(organization: str) -> bool:
    if not organization or not network_ready():
        return False
    return CommunitySettings.objects.filter(organization=organization, enabled=True).exists()


def _urls_in(body_text: str, body_html: str) -> list[str]:
    return list(dict.fromkeys(
        u.rstrip(".,;:") for u in URL_RE.findall(f"{body_text or ''} {body_html or ''}")))


def _host_of(url: str) -> str:
    try:
        return normalize_domain(urlsplit(url).hostname or "")
    except ValueError:
        return ""


# ── Coincidencia al analizar ──────────────────────────────
def match_email(organization, from_header, body_text, body_html="") -> dict | None:
    """Busca el correo en la copia local del feed. No hace llamadas de red."""
    if not is_enabled(organization):
        return None

    candidates = set()
    domains = {normalize_domain(domain_from_header(from_header))}
    for url in _urls_in(body_text, body_html):
        try:
            candidates.add(ioc_hash(normalize_url(url)))
        except ValueError:
            continue
        domains.add(_host_of(url))
    candidates |= {ioc_hash(d) for d in domains if d and d not in EXCLUDED_DOMAINS}

    matches = list(CommunityIndicator.objects.filter(ioc_hash__in=candidates))
    if not matches:
        return None

    own = CommunitySettings.objects.filter(organization=organization).first()
    company_count = max(m.company_count for m in matches)
    sectors = sorted({s for m in matches for s in m.sectors})
    regions = sorted({r for m in matches for r in m.regions})
    scope = "de tu sector" if own and own.sector in sectors else "de la red"
    companies = f"{company_count} {'empresa' if company_count == 1 else 'empresas'} {scope}"
    message = (f"Este dominio o enlace fue reportado por {companies} en los últimos días."
               if len(matches) == 1 else
               f"Este correo tiene dominios o enlaces reportados por {companies} en los últimos días.")
    return {
        "company_count": company_count,
        "sectors": sectors,
        "regions": regions,
        "first_seen": min(m.first_seen for m in matches).isoformat(),
        "message": message,
    }


def should_elevate(signal: dict | None) -> bool:
    return bool(signal) and signal["company_count"] >= ELEVATE_FROM_COMPANIES


# ── Candidatos a compartir ────────────────────────────────
def _org_supplier_domains(organization: str) -> set[str]:
    domains = set()
    for values in Supplier.objects.filter(organization=organization) \
            .values_list("email_domains", flat=True):
        domains.update(values or [])
    return domains


def record_outbox(alert, organization, email_payload, ml_result) -> int:
    """Calcula las huellas de una alerta. Solo corre si la empresa ya dio su consentimiento."""
    if alert is None or not is_enabled(organization):
        return 0

    headers = email_payload.get("headers", {})
    excluded = EXCLUDED_DOMAINS | _org_supplier_domains(organization)
    entries = {}

    domain = normalize_domain(domain_from_header(headers.get("from", "")))
    # No acuses a un proveedor propio: su correo pudo ser suplantado o estar comprometido
    if domain and domain not in excluded:
        entries[ioc_hash(domain)] = "domain"

    full_urls = _urls_in(email_payload.get("body_text", ""), email_payload.get("body_html", ""))
    for analyzed in ml_result.get("urls_analyzed", []):
        if analyzed.get("score", 0) < MIN_URL_SCORE:
            continue
        truncated = analyzed.get("url_truncated", "")
        # El motor ML devuelve solo 80 caracteres: recupera la URL completa del cuerpo
        url = next((u for u in full_urls if u.startswith(truncated)), truncated)
        try:
            normalized = normalize_url(url)
        except ValueError:
            continue
        if normalized and _host_of(url) not in EXCLUDED_DOMAINS:
            entries[ioc_hash(normalized)] = "url"

    for hash_value, kind in entries.items():
        OutboxEntry.objects.get_or_create(
            alert=alert, ioc_hash=hash_value,
            defaults={"organization": organization, "ioc_type": kind})
    return len(entries)


def _report_for(entry, community: CommunitySettings) -> dict:
    """Lo único que sale hacia el hub. Revisa el texto de consentimiento si lo cambias."""
    alert = entry.alert
    return {
        "ioc_type": entry.ioc_type,
        "ioc_hash": entry.ioc_hash,
        "phishing_type": alert.phishing_type,
        # El hub solo acepta T1566 y sus subtécnicas
        "mitre_technique": alert.mitre_technique or "T1566",
        "severity": alert.severity,
        "sector": community.sector,
        "region": community.region,
        "observed_on": timezone.localtime(alert.detected_at).date().isoformat(),
    }


def _shareable_entries(organization):
    # "Confirmada por un analista" es resolved; false_pos nunca se comparte
    return (OutboxEntry.objects.select_related("alert")
            .filter(organization=organization, sent_at__isnull=True)
            .exclude(alert__status=Alert.Status.FALSE_POS)
            .filter(Q(alert__risk_score__gte=MIN_SHARE_SCORE)
                    | Q(alert__status=Alert.Status.RESOLVED)))


# ── Comunicación con el hub ───────────────────────────────
class HubError(Exception):
    def __init__(self, status_value, message):
        super().__init__(message)
        self.status_value = status_value
        self.message = message


def _hub_request(method, path, json=None, params=None, hub_url=None, api_key=None):
    url = f"{(hub_url or settings.COMMUNITY_HUB_URL).rstrip('/')}{path}"
    key = api_key if api_key is not None else settings.COMMUNITY_NODE_API_KEY
    try:
        response = httpx.request(method, url, json=json, params=params,
                                 headers={"X-Node-Key": key}, timeout=HUB_TIMEOUT)
    except httpx.HTTPError as exc:
        logger.warning(f"[Comunidad] El hub no responde: {exc}")
        raise HubError(CommunitySettings.NodeStatus.UNREACHABLE, "El hub no responde.")
    if response.status_code in (401, 403):
        raise HubError(CommunitySettings.NodeStatus.SUSPENDED,
                       "El hub rechazó la key del nodo o lo suspendió.")
    if response.status_code == 429:
        raise HubError(CommunitySettings.NodeStatus.ACTIVE, "Se alcanzó el límite diario del hub.")
    if response.status_code >= 400:
        raise HubError(CommunitySettings.NodeStatus.UNREACHABLE,
                       f"El hub respondió con error {response.status_code}.")
    return response


def push_indicators() -> int:
    """Envía los indicadores nuevos de cada empresa con opt-in."""
    sent = 0
    for community in CommunitySettings.objects.filter(enabled=True):
        # Sin sector o región el hub rechazaría el lote: no gastes el cupo diario
        if not (community.sector and community.region):
            continue
        while True:
            batch = list(_shareable_entries(community.organization)[:BATCH_SIZE])
            if not batch:
                break
            _hub_request("POST", "/indicators",
                         json={"indicators": [_report_for(e, community) for e in batch]})
            OutboxEntry.objects.filter(pk__in=[e.pk for e in batch]).update(sent_at=timezone.now())
            sent += len(batch)
    return sent


def pull_feed(hub_url=None, api_key=None) -> int:
    """Actualiza la copia local. Borra lo que ya no publica el hub (p. ej. revocaciones)."""
    since = timezone.localdate() - timedelta(days=FEED_WINDOW_DAYS)
    response = _hub_request("GET", "/feed", params={"since": since.isoformat()},
                            hub_url=hub_url, api_key=api_key)
    items = response.json().get("indicators", [])
    hashes = [item["ioc_hash"] for item in items]
    with transaction.atomic():
        for item in items:
            CommunityIndicator.objects.update_or_create(
                ioc_hash=item["ioc_hash"],
                defaults={field: item[field] for field in (
                    "ioc_type", "company_count", "sectors", "regions", "phishing_type",
                    "mitre_technique", "first_seen", "last_seen")},
            )
        CommunityIndicator.objects.exclude(ioc_hash__in=hashes).delete()
    return len(items)


def _set_status(community, node_status, error=""):
    community.node_status = node_status
    community.last_error = error[:200]
    update = ["node_status", "last_error"]
    if node_status == CommunitySettings.NodeStatus.ACTIVE and not error:
        community.last_sync_at = timezone.now()
        update.append("last_sync_at")
    community.save(update_fields=update)


def _retry_pending_deletions():
    for community in CommunitySettings.objects.filter(deletion_pending=True):
        try:
            _hub_request("DELETE", "/nodes/me/indicators")
        except HubError as exc:
            logger.warning(f"[Comunidad] Sigue pendiente borrar aportes: {exc.message}")
            return
        community.deletion_pending = False
        community.save(update_fields=["deletion_pending"])
        _mark_other_orgs_for_resend(community.organization)


def sync() -> dict:
    """Tarea periódica: nunca lanza excepciones por culpa del hub."""
    enabled = CommunitySettings.objects.filter(enabled=True)
    pending = CommunitySettings.objects.filter(deletion_pending=True).exists()
    if not enabled.exists() and not pending:
        return {"skipped": "sin empresas con la red activa"}
    if not hub_ready() or not network_ready():
        logger.warning("[Comunidad] Faltan COMMUNITY_HUB_URL, COMMUNITY_NODE_API_KEY "
                       "o COMMUNITY_NETWORK_KEY: no se sincroniza.")
        enabled.update(node_status=CommunitySettings.NodeStatus.NOT_CONFIGURED)
        return {"skipped": "sin configuración"}

    _retry_pending_deletions()
    if not enabled.exists():
        return {"pushed": 0, "pulled": 0}
    try:
        pushed = push_indicators()
        pulled = pull_feed()
    except HubError as exc:
        logger.warning(f"[Comunidad] Sincronización incompleta: {exc.message}")
        for community in enabled:
            _set_status(community, exc.status_value, exc.message)
        return {"error": exc.message}
    for community in enabled:
        _set_status(community, CommunitySettings.NodeStatus.ACTIVE)
    return {"pushed": pushed, "pulled": pulled}


# ── Consentimiento ────────────────────────────────────────
def enable(community, user, sector, region):
    community.enabled = True
    community.sector = sector
    community.region = region
    community.consent_accepted_by = user
    community.consent_accepted_at = timezone.now()
    community.consent_version = CONSENT_VERSION
    community.node_status = (CommunitySettings.NodeStatus.ACTIVE if hub_ready() and network_ready()
                             else CommunitySettings.NodeStatus.NOT_CONFIGURED)
    community.save()


def _mark_other_orgs_for_resend(organization):
    # El hub borra por nodo y una instalación es un solo nodo: si otra empresa de esta
    # instalación sigue activa, sus aportes también se borraron y hay que reenviarlos.
    others = CommunitySettings.objects.filter(enabled=True).exclude(organization=organization) \
        .values_list("organization", flat=True)
    OutboxEntry.objects.filter(organization__in=list(others)).update(sent_at=None)


def disable(community) -> bool:
    """Devuelve True si el hub confirmó el borrado; si no, queda pendiente de reintento."""
    community.enabled = False
    community.node_status = CommunitySettings.NodeStatus.DISABLED
    community.save(update_fields=["enabled", "node_status"])
    had_shared = OutboxEntry.objects.filter(organization=community.organization,
                                            sent_at__isnull=False).exists()
    OutboxEntry.objects.filter(organization=community.organization).delete()

    if not CommunitySettings.objects.filter(enabled=True).exists():
        CommunityIndicator.objects.all().delete()
    if not had_shared:
        return True
    if not hub_ready():
        community.deletion_pending = True
        community.save(update_fields=["deletion_pending"])
        return False
    try:
        _hub_request("DELETE", "/nodes/me/indicators")
    except HubError as exc:
        logger.warning(f"[Comunidad] No se pudo pedir el borrado: {exc.message}")
        community.deletion_pending = True
        community.save(update_fields=["deletion_pending"])
        return False
    _mark_other_orgs_for_resend(community.organization)
    return True


# ── Tarjeta del dashboard ─────────────────────────────────
def summary(organization) -> dict:
    community = CommunitySettings.objects.filter(organization=organization).first()
    if community is None or not community.enabled:
        return {"enabled": False, "active_campaigns": 0, "matches": 0}
    # La fecha del feed no trae hora: "últimas 24 h" incluye hoy y ayer
    since = timezone.localdate() - timedelta(days=1)
    campaigns = [i for i in CommunityIndicator.objects.filter(last_seen__gte=since)
                 if community.sector in i.sectors and community.region in i.regions]
    matches = Alert.objects.filter(owner__organization=organization,
                                   detected_at__gte=timezone.now() - timedelta(hours=24),
                                   risk_signals__has_key="community").count()
    return {
        "enabled": True, "sector": community.sector, "region": community.region,
        "active_campaigns": len(campaigns), "matches": matches,
        "last_sync_at": community.last_sync_at, "node_status": community.node_status,
    }
