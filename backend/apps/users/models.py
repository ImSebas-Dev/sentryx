"""
Sentryx v2 — Modelo de usuario actualizado.
Añade:
    - email único obligatorio
    - is_email_verified: verificación por correo
    - email_verification_token / password_reset_token
    - organization (para mostrar en el panel de admin)
"""
import hashlib
import uuid
import secrets
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from datetime import timedelta


def _token():
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    """
    Los tokens de los enlaces se guardan solo como SHA-256: quien lea la base de
    datos (copia de seguridad, inyección SQL) no puede usarlos para entrar.
    """
    return hashlib.sha256((token or "").encode()).hexdigest()


def _token_matches(stored: str, token: str) -> bool:
    return bool(stored and token) and constant_time_compare(stored, hash_token(token))


class ShieldUser(AbstractUser):

    class Role(models.TextChoices):
        ADMIN   = "admin",   "Administrador"
        ANALYST = "analyst", "Analista"
        VIEWER  = "viewer",  "Viewer (solo lectura)"

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role         = models.CharField(max_length=10, choices=Role.choices, default=Role.ANALYST)
    organization = models.CharField(max_length=120, blank=True,
                        help_text="Empresa u organización del usuario")

    # ── Email obligatorio y único ─────────────────────────
    email = models.EmailField(unique=True, blank=False,
                help_text="Correo corporativo o personal — se usará para verificación")

    # ── Estados de la cuenta ──────────────────────────────
    is_email_verified = models.BooleanField(default=False,
                            help_text="El usuario confirmó su correo")

    # ── Tokens de un solo uso ─────────────────────────────
    email_verification_token    = models.CharField(max_length=100, blank=True, default=_token)
    email_verification_sent_at  = models.DateTimeField(null=True, blank=True)

    password_reset_token        = models.CharField(max_length=100, blank=True)
    password_reset_sent_at      = models.DateTimeField(null=True, blank=True)

    # ── Aceptación de términos (requerido en registro) ────
    accepted_terms    = models.BooleanField(default=False)
    accepted_terms_at = models.DateTimeField(null=True, blank=True)

    # ── Autenticación de dos factores (TOTP) ──────────────
    # mfa_secret va cifrado con Fernet. No leerlo ni escribirlo directamente:
    # usar las funciones de apps/users/mfa.py (start_setup, verify_totp...).
    mfa_enabled        = models.BooleanField(default=False)
    mfa_secret         = models.TextField(blank=True, default="")
    mfa_recovery_codes = models.JSONField(default=list, blank=True,
                             help_text="HMAC-SHA256 de los códigos de recuperación sin usar")
    mfa_enabled_at     = models.DateTimeField(null=True, blank=True)

    # ── Metadata ──────────────────────────────────────────
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    # Requerir username único pero generarlo del email si no se proporciona
    USERNAME_FIELD  = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        db_table            = "shield_users"
        verbose_name        = "Usuario"
        verbose_name_plural = "Usuarios"

    def __str__(self):
        return f"{self.email} ({self.get_role_display()})"

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_analyst(self):
        return self.role in (self.Role.ADMIN, self.Role.ANALYST)

    @property
    def mfa_setup_required(self):
        """Admin sin 2FA cuando la política lo exige: solo puede configurarlo."""
        from django.conf import settings
        return bool(settings.MFA_REQUIRED_FOR_ADMINS and self.is_admin
                    and not self.mfa_enabled)

    @property
    def can_login(self):
        """Un usuario solo puede entrar si está activo y verificó el correo."""
        return self.is_active and self.is_email_verified

    # ── Helpers de tokens ─────────────────────────────────
    # rotate_* devuelve el token en claro UNA vez (para el correo) y guarda su hash.
    def rotate_verification_token(self):
        token = _token()
        self.email_verification_token   = hash_token(token)
        self.email_verification_sent_at = timezone.now()
        self.save(update_fields=["email_verification_token", "email_verification_sent_at"])
        return token

    def is_verification_token_valid(self, token: str) -> bool:
        if not self.email_verification_sent_at:
            return False
        if not _token_matches(self.email_verification_token, token):
            return False
        expires = self.email_verification_sent_at + timedelta(
            hours=settings.EMAIL_VERIFICATION_TIMEOUT_HOURS)
        return timezone.now() < expires

    def rotate_reset_token(self):
        token = _token()
        self.password_reset_token   = hash_token(token)
        self.password_reset_sent_at = timezone.now()
        self.save(update_fields=["password_reset_token", "password_reset_sent_at"])
        return token

    def is_reset_token_valid(self, token: str) -> bool:
        if not self.password_reset_sent_at:
            return False
        if not _token_matches(self.password_reset_token, token):
            return False
        expires = self.password_reset_sent_at + timedelta(
            minutes=settings.PASSWORD_RESET_TIMEOUT_MINUTES)
        return timezone.now() < expires

    def email_cooldown_active(self, sent_at) -> bool:
        """True si se envió un correo de cuenta hace menos de AUTH_EMAIL_COOLDOWN_SECONDS."""
        cooldown = settings.AUTH_EMAIL_COOLDOWN_SECONDS
        return bool(cooldown and sent_at
                    and timezone.now() < sent_at + timedelta(seconds=cooldown))

    def clear_reset_token(self):
        self.password_reset_token   = ""
        self.password_reset_sent_at = None
        self.save(update_fields=["password_reset_token", "password_reset_sent_at"])
