"""
Sentryx v2 — Autenticación JWT con la política de 2FA para administradores.

Si MFA_REQUIRED_FOR_ADMINS=True, el login de un admin sin 2FA entrega tokens
con el claim mfa_setup_required. Esos tokens solo sirven para leer el perfil
y configurar el 2FA; cualquier otro endpoint responde 403 con
code=mfa_setup_required (el frontend redirige a "Seguridad de la cuenta").
"""
from django.conf import settings
from rest_framework import exceptions
from rest_framework_simplejwt.authentication import JWTAuthentication

# Rutas permitidas con un token mfa_setup_required. Mantener alineado con
# MFA_SETUP_PATHS del frontend (src/services/api.js).
SETUP_ALLOWED_PATHS = (
    "/api/v1/auth/me/",
    "/api/v1/auth/mfa/setup/",
    "/api/v1/auth/mfa/enable/",
)


MFA_SETUP_MESSAGE = ("Debes activar la verificación en dos pasos antes de "
                     "usar Sentryx con una cuenta de administrador.")


class ShieldJWTAuthentication(JWTAuthentication):

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, token = result
        if (token.get("mfa_setup_required")
                and user.mfa_setup_required
                and request.path not in SETUP_ALLOWED_PATHS):
            # Pasar un dict para que la respuesta incluya "code": DRF no lo
            # añade al cuerpo con el manejador de excepciones por defecto.
            raise exceptions.PermissionDenied(
                {"detail": MFA_SETUP_MESSAGE, "code": "mfa_setup_required"}
            )
        return user, token
