"""
Sentryx v2 — Utilidades compartidas de auditoría y seguridad.

client_ip() es la única forma correcta de obtener la IP del cliente: úsala en
vistas, middleware, django-axes y el throttling. No leas X-Forwarded-For a mano.
"""
import logging

from django.conf import settings

security_logger = logging.getLogger("sentryx.security")


def client_ip(request) -> str:
    """
    IP real del cliente detrás de los proxies confiables (NUM_PROXIES).

    nginx AÑADE la IP que ve al final de X-Forwarded-For, así que la entrada
    confiable es la N-ésima desde el final. La primera entrada la escribe el
    cliente y se puede falsificar: nunca la uses para auditoría ni bloqueos.
    """
    request = getattr(request, "_request", request)  # Request de DRF → HttpRequest
    meta = getattr(request, "META", {}) or {}
    num_proxies = settings.REST_FRAMEWORK.get("NUM_PROXIES") or 0
    forwarded = meta.get("HTTP_X_FORWARDED_FOR", "")
    if num_proxies and forwarded:
        addrs = [a.strip() for a in forwarded.split(",") if a.strip()]
        if addrs:
            return addrs[-min(num_proxies, len(addrs))]
    return meta.get("REMOTE_ADDR", "") or ""


def axes_username(request, credentials=None) -> str:
    """
    Cuenta que intenta entrar, para django-axes. La API envía "email" y el login
    de /admin/ envía "username" (que en Sentryx también es el correo).
    """
    credentials = credentials or {}
    for key in ("email", "username"):
        if credentials.get(key):
            return str(credentials[key]).strip().lower()
    post = getattr(request, "POST", None) or {}
    for key in ("email", "username"):
        if post.get(key):
            return str(post[key]).strip().lower()
    return ""


def log_security_event(event: str, request=None, level=logging.WARNING, **fields):
    """
    Deja un evento de seguridad en el log estructurado (logger sentryx.security).
    No incluyas contraseñas, tokens ni el contenido de correos en fields.
    """
    if request is not None:
        fields.setdefault("ip", client_ip(request))
        fields.setdefault("path", getattr(request, "path", ""))
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            fields.setdefault("user", str(user.pk))
    detail = " ".join(f"{k}={v!r}" for k, v in sorted(fields.items()))
    security_logger.log(level, "event=%s %s", event, detail)
