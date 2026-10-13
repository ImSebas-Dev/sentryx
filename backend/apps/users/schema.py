"""
Sentryx v2 — Extensiones de drf-spectacular.
Se importa en UsersConfig.ready(); no importarlo desde otros módulos.
"""
from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme


class ShieldJWTScheme(SimpleJWTScheme):
    """Documentar ShieldJWTAuthentication como Bearer JWT (igual que SimpleJWT)."""
    target_class = "apps.users.authentication.ShieldJWTAuthentication"
    name = "jwtAuth"
