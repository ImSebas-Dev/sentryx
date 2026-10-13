"""Sentryx v2 — Serializers de usuarios y autenticación."""
from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()


class ShieldTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    JWT personalizado — incluye rol y organización en el payload.
    Permite al frontend saber el rol del usuario sin petición adicional.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"]         = user.role
        token["organization"] = user.organization
        return token


def issue_tokens(user, mfa_setup_required=False) -> dict:
    """
    Emitir el par JWT. Usar esta función en todo login (contraseña o 2FA)
    para que los claims sean iguales en ambos caminos.
    SimpleJWT copia los claims del refresh al access, así que el claim
    mfa_setup_required también sobrevive a /token/refresh/.
    """
    refresh = ShieldTokenObtainPairSerializer.get_token(user)
    if mfa_setup_required:
        refresh["mfa_setup_required"] = True
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


class UserMeSerializer(serializers.ModelSerializer):
    """Perfil completo del usuario autenticado — GET /auth/me/"""

    class Meta:
        model  = User
        fields = [
            "id", "username", "email", "role", "organization",
            "first_name", "last_name", "date_joined",
            "is_email_verified", "is_approved",
            "mfa_enabled", "mfa_enabled_at", "mfa_setup_required",
            "mfa_recovery_codes_remaining",
        ]
        # No quitar role ni email de esta lista: el propio usuario podría
        # volverse admin con PATCH /auth/me/ {"role": "admin"}.
        read_only_fields = ["id", "username", "email", "role", "date_joined",
                            "is_email_verified", "is_approved",
                            "mfa_enabled", "mfa_enabled_at"]

    mfa_setup_required = serializers.BooleanField(read_only=True)
    mfa_recovery_codes_remaining = serializers.SerializerMethodField()

    def get_mfa_recovery_codes_remaining(self, obj) -> int:
        return len(obj.mfa_recovery_codes or [])


class UserListSerializer(serializers.ModelSerializer):
    """
    Lista de usuarios para el panel de administración.
    Incluye email y created_at necesarios para la página de usuarios pendientes.
    """

    class Meta:
        model  = User
        fields = [
            "id", "username", "email", "role", "organization",
            "is_active", "is_email_verified", "is_approved", "mfa_enabled",
            "date_joined", "last_login", "created_at",
        ]
        read_only_fields = fields
