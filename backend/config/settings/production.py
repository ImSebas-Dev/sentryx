"""
Sentryx v2 — Settings de producción.

Uso: DJANGO_SETTINGS_MODULE=config.settings.production (docker-compose.prod.yml).
El backend se niega a arrancar si falta un secreto o si conserva un valor de
desarrollo publicado en el repositorio.
"""
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa
from .base import config

DEBUG = False

# Valores publicados en .env.example, setup.sh o el historial de Git: cualquiera
# que haya visto el repositorio los conoce. Ver docs/seguridad.md (rotación).
KNOWN_DEV_VALUES = {
    "sentryx-dev-secret-key-2026-cambiar-en-produccion",
    "sentryx-dev-mfa-key-2026-cambiar-en-produccion",
    "salt-unico-sentryx-2026", "mlkey123", "dev-key",
    "sentryx123", "sentryx_dev_pwd", "redis123", "sentryx_redis_pwd",
    "community_dev_pwd",
}


def _require_secret(name, value, min_length=32):
    if not value or len(value) < min_length or value in KNOWN_DEV_VALUES:
        raise ImproperlyConfigured(
            f"{name} falta, es corto (< {min_length}) o es un valor de desarrollo conocido. "
            "Genera uno con: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )


_require_secret("DJANGO_SECRET_KEY", SECRET_KEY, 50)  # noqa: F405
_require_secret("PSEUDONYMIZATION_SALT", PSEUDONYMIZATION_SALT)  # noqa: F405
_require_secret("ML_ENGINE_API_KEY", ML_ENGINE_API_KEY)  # noqa: F405
_require_secret("MFA_ENCRYPTION_KEY", MFA_ENCRYPTION_KEY)  # noqa: F405
_require_secret("POSTGRES_PASSWORD", DATABASES["default"]["PASSWORD"], 16)  # noqa: F405

if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS debe listar los dominios públicos (sin '*').")
if any(o.startswith("http://") for o in CORS_ALLOWED_ORIGINS):  # noqa: F405
    raise ImproperlyConfigured("CORS_ALLOWED_ORIGINS solo admite orígenes https:// en producción.")

# ── HTTPS obligatorio ─────────────────────────────────────
# nginx termina TLS y envía X-Forwarded-Proto. Confía en esa cabecera solo
# porque el backend no publica su puerto: únicamente nginx puede llegar a él.
SECURE_PROXY_SSL_HEADER        = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT            = True
SECURE_REDIRECT_EXEMPT         = [r"^api/v1/health/$"]  # healthcheck interno del contenedor
SECURE_HSTS_SECONDS            = config("SECURE_HSTS_SECONDS", default=31536000, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD            = config("SECURE_HSTS_PRELOAD", default=False, cast=bool)
USE_X_FORWARDED_HOST           = False

# ── Cookies solo por HTTPS ────────────────────────────────
SESSION_COOKIE_SECURE      = True
CSRF_COOKIE_SECURE         = True
AUTH_REFRESH_COOKIE_SECURE = True
# El __Host- obliga al navegador a exigir Secure, Path=/ y sin Domain
SESSION_COOKIE_NAME        = "__Host-sessionid"
CSRF_COOKIE_NAME           = "__Host-csrftoken"
if not CSRF_TRUSTED_ORIGINS:  # noqa: F405
    CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS if not h.startswith(".")]  # noqa: F405

# ── Políticas más estrictas ───────────────────────────────
MFA_REQUIRED_FOR_ADMINS = config("MFA_REQUIRED_FOR_ADMINS", default=True, cast=bool)

# Correo real: sin SendGrid nadie recibiría los enlaces de verificación
if not SENDGRID_API_KEY:  # noqa: F405
    import warnings
    warnings.warn("SENDGRID_API_KEY vacío: no se enviarán correos de verificación ni de recuperación.")
