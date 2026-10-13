"""
Sentryx v2 — Servicio de autenticación de dos factores (TOTP, RFC 6238).

Compatible con Google Authenticator y Microsoft Authenticator (SHA-1,
6 dígitos, periodo de 30 s, que es lo único que ambas apps soportan).

Piezas:
  - Secreto TOTP cifrado en reposo con Fernet. La clave se deriva de
    settings.MFA_ENCRYPTION_KEY con SHA-256.
  - Códigos de recuperación: se guardan solo como HMAC-SHA256 y se borran
    al usarse.
  - mfa_token: token firmado (django.core.signing) que el login entrega en
    lugar del JWT. Su jti vive en caché (Redis) con el contador de intentos;
    borrar la clave de caché es lo que lo hace de un solo uso.
"""
import base64
import hashlib
import io
import secrets
import uuid
from datetime import timedelta

import pyotp
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

LOGIN_TOKEN_SALT   = "sentryx.mfa.login"
RECOVERY_HMAC_SALT = "sentryx.mfa.recovery"
# Alfabeto sin caracteres ambiguos (0/o, 1/l/i) para dictar los códigos
RECOVERY_ALPHABET  = "abcdefghjkmnpqrstuvwxyz23456789"


class MFAConfigurationError(Exception):
    """MFA_ENCRYPTION_KEY no está configurada."""


class MFATokenError(Exception):
    """mfa_token inválido, expirado, ya usado o sin intentos."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


# ── Cifrado del secreto ───────────────────────────────────
def is_configured() -> bool:
    return bool(settings.MFA_ENCRYPTION_KEY)


def _fernet() -> Fernet:
    if not is_configured():
        raise MFAConfigurationError(
            "MFA_ENCRYPTION_KEY no está configurada en el entorno."
        )
    digest = hashlib.sha256(settings.MFA_ENCRYPTION_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        # La clave cambió desde que se guardó el secreto: el usuario debe
        # volver a activar el 2FA (o un admin restablecerlo).
        raise MFAConfigurationError(
            "No se pudo descifrar el secreto 2FA: MFA_ENCRYPTION_KEY cambió."
        )


# ── TOTP ──────────────────────────────────────────────────
def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(user, secret: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(
        name=user.email, issuer_name=settings.MFA_ISSUER,
    )


def qr_data_uri(uri: str) -> str:
    import qrcode
    img = qrcode.make(uri, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _normalize_code(code) -> str:
    return "".join(str(code or "").split())


def verify_totp(user, code, secret: str = None) -> bool:
    """
    Verificar un código TOTP con ventana ±1 (±30 s de desfase de reloj).
    Rechazar el reuso del mismo intervalo: un código ya aceptado no vale
    una segunda vez aunque siga dentro de la ventana.
    """
    code = _normalize_code(code)
    if not (code.isdigit() and len(code) == 6):
        return False
    secret = secret or decrypt_secret(user.mfa_secret)
    totp = pyotp.TOTP(secret)
    now = timezone.now()
    for offset in (-1, 0, 1):
        at = now + timedelta(seconds=offset * totp.interval)
        if constant_time_compare(totp.at(at), code):
            step = totp.timecode(at)
            key = f"mfa:last_step:{user.pk}"
            last = cache.get(key)
            if last is not None and step <= last:
                return False
            cache.set(key, step, timeout=totp.interval * 3)
            return True
    return False


# ── Códigos de recuperación ───────────────────────────────
def _normalize_recovery(code) -> str:
    return _normalize_code(code).replace("-", "").lower()


def hash_recovery_code(code: str) -> str:
    return salted_hmac(
        RECOVERY_HMAC_SALT, _normalize_recovery(code),
        secret=settings.MFA_ENCRYPTION_KEY, algorithm="sha256",
    ).hexdigest()


def generate_recovery_codes(n: int = None):
    """Devolver (códigos en claro, hashes). Los códigos en claro no se guardan."""
    n = n or settings.MFA_RECOVERY_CODES
    plain = []
    for _ in range(n):
        raw = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(10))
        plain.append(f"{raw[:5]}-{raw[5:]}")
    return plain, [hash_recovery_code(c) for c in plain]


def consume_recovery_code(user, code) -> int | None:
    """
    Usar un código de recuperación. Devolver los que quedan, o None si el
    código no es válido. Bloquear la fila para que dos peticiones simultáneas
    no puedan usar el mismo código.
    """
    if len(_normalize_recovery(code)) != 10:
        return None
    target = hash_recovery_code(code)
    User = type(user)
    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=user.pk)
        codes = list(locked.mfa_recovery_codes or [])
        match = next((h for h in codes if constant_time_compare(h, target)), None)
        if match is None:
            return None
        codes.remove(match)
        locked.mfa_recovery_codes = codes
        locked.save(update_fields=["mfa_recovery_codes"])
    user.mfa_recovery_codes = codes
    return len(codes)


# ── Activar / desactivar ──────────────────────────────────
def start_setup(user) -> dict:
    """Generar un secreto nuevo sin activar el 2FA todavía."""
    secret = new_secret()
    user.mfa_secret = encrypt_secret(secret)
    user.save(update_fields=["mfa_secret"])
    uri = provisioning_uri(user, secret)
    return {"secret": secret, "otpauth_url": uri, "qr_code": qr_data_uri(uri)}


def enable(user):
    plain, hashes = generate_recovery_codes()
    user.mfa_enabled = True
    user.mfa_enabled_at = timezone.now()
    user.mfa_recovery_codes = hashes
    user.save(update_fields=["mfa_enabled", "mfa_enabled_at", "mfa_recovery_codes"])
    return plain


def disable(user):
    user.mfa_enabled = False
    user.mfa_enabled_at = None
    user.mfa_secret = ""
    user.mfa_recovery_codes = []
    user.save(update_fields=["mfa_enabled", "mfa_enabled_at",
                             "mfa_secret", "mfa_recovery_codes"])


# ── Token del segundo paso del login ──────────────────────
def _jti_key(jti: str) -> str:
    return f"mfa:login:{jti}"


def issue_login_token(user) -> str:
    jti = uuid.uuid4().hex
    cache.set(_jti_key(jti), 0, timeout=settings.MFA_LOGIN_TOKEN_MAX_AGE)
    return signing.dumps({"uid": str(user.pk), "jti": jti}, salt=LOGIN_TOKEN_SALT)


def read_login_token(token: str) -> dict:
    """Validar firma, caducidad y que el token siga sin usar."""
    try:
        payload = signing.loads(token or "", salt=LOGIN_TOKEN_SALT,
                                max_age=settings.MFA_LOGIN_TOKEN_MAX_AGE)
    except signing.SignatureExpired:
        raise MFATokenError("mfa_token_expired",
                            "La verificación expiró. Inicia sesión de nuevo.")
    except signing.BadSignature:
        raise MFATokenError("mfa_token_invalid",
                            "La verificación no es válida. Inicia sesión de nuevo.")
    if cache.get(_jti_key(payload["jti"])) is None:
        raise MFATokenError("mfa_token_used",
                            "Esta verificación ya se usó o expiró. Inicia sesión de nuevo.")
    return payload


def register_attempt(payload) -> int:
    """
    Sumar un intento al mfa_token y devolver el número de intento actual.
    Al pasar el máximo, invalidar el token.
    """
    key = _jti_key(payload["jti"])
    try:
        attempt = cache.incr(key)
    except ValueError:
        raise MFATokenError("mfa_token_used",
                            "Esta verificación ya se usó o expiró. Inicia sesión de nuevo.")
    if attempt > settings.MFA_MAX_ATTEMPTS:
        cache.delete(key)
        raise MFATokenError("mfa_too_many_attempts",
                            "Demasiados códigos incorrectos. Inicia sesión de nuevo.")
    return attempt


def consume_login_token(payload) -> bool:
    """Invalidar el token. False si otra petición lo consumió antes."""
    return bool(cache.delete(_jti_key(payload["jti"])))
