from django.apps import AppConfig
from django.core import checks


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users"

    def ready(self):
        checks.register(check_mfa_settings, checks.Tags.security)
        from apps.users import schema  # noqa: F401  (registra la extensión OpenAPI)


def check_mfa_settings(app_configs, **kwargs):
    """Avisar al arrancar si el 2FA no puede funcionar (sale en migrate y runserver)."""
    from django.conf import settings
    if settings.MFA_ENCRYPTION_KEY:
        return []
    level = checks.Error if settings.MFA_REQUIRED_FOR_ADMINS else checks.Warning
    return [level(
        "MFA_ENCRYPTION_KEY no está configurada: la verificación en dos pasos "
        "queda deshabilitada (los endpoints /auth/mfa/ responden 503).",
        hint="Añadir MFA_ENCRYPTION_KEY al .env (ver .env.example) y reiniciar el backend.",
        id="sentryx.W001" if level is checks.Warning else "sentryx.E001",
    )]
