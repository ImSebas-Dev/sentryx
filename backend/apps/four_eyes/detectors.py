"""
Sentryx v2 — Detectores de la política de cuatro ojos.

Son reglas sencillas y a propósito fáciles de leer. Amplía las constantes cuando
aparezca un patrón nuevo; escribe las frases sin tildes y en minúsculas porque el
texto se normaliza antes de comparar.
"""
import re

from apps.payment_shield.invoice import zip_is_encrypted
from apps.payment_shield.services import email_text, normalize_text

CREDENTIAL_KEYWORDS = [
    "iniciar sesion", "inicia sesion", "inicie sesion", "ingresa tu usuario",
    "ingrese su usuario", "ingresa tu clave", "ingrese su clave", "verificar la cuenta",
    "verifica tu cuenta", "verifique su cuenta", "verificar tu cuenta", "validar tu cuenta",
    "valida tu cuenta", "valide su cuenta", "actualizar datos", "actualiza tus datos",
    "actualice sus datos", "confirma tu contrasena", "confirme su contrasena",
    "restablecer tu contrasena", "cambia tu contrasena", "tu cuenta sera suspendida",
    "tu cuenta sera bloqueada",
]
LOGIN_URL_RE = re.compile(
    r"https?://[^\s\"'<>]*(?:login|signin|sign-in|logon|wp-login|verify|verificar|"
    r"autenticar|auth/|password|contrasena)[^\s\"'<>]*", re.IGNORECASE)
PASSWORD_FIELD_RE = re.compile(r"<input[^>]+type=[\"']?password", re.IGNORECASE)

RISKY_EXTENSIONS = (".exe", ".js", ".vbs", ".scr", ".iso", ".lnk", ".html", ".htm",
                    ".docm", ".xlsm")
COMPRESSED_EXTENSIONS = (".zip", ".rar")
# Los RAR no se abren aquí: se reconocen porque el correo entrega la clave en el texto.
PASSWORD_HINT_RE = re.compile(r"\b(?:contrasena|clave|password)\b")


def detect_credential_request(body_text: str, body_html: str = "") -> list[str]:
    """Devuelve lo que indica que el correo pide credenciales."""
    normalized = normalize_text(email_text(body_text, body_html))
    found = [kw for kw in CREDENTIAL_KEYWORDS if kw in normalized]
    raw = f"{body_text or ''} {body_html or ''}"
    if PASSWORD_FIELD_RE.search(raw):
        found.append("formulario que pide contraseña")
    elif LOGIN_URL_RE.search(raw):
        found.append("enlace a una página de inicio de sesión")
    return found


def _encrypted_uploads(attachments) -> set[str]:
    names = set()
    for upload in attachments:
        name = (getattr(upload, "name", "") or "").lower()
        if not name.endswith(".zip"):
            continue
        upload.seek(0)
        if zip_is_encrypted(upload.read()):
            names.add(name)
        upload.seek(0)
    return names


def detect_risky_attachments(names, attachments=(), body_text="", body_html="") -> list[str]:
    """Devuelve los nombres de los adjuntos de riesgo."""
    normalized = normalize_text(email_text(body_text, body_html))
    mentions_password = bool(PASSWORD_HINT_RE.search(normalized))
    encrypted = _encrypted_uploads(attachments)
    risky = []
    for name in names or []:
        lower = (name or "").lower().strip()
        if lower.endswith(RISKY_EXTENSIONS):
            risky.append(name)
        elif lower.endswith(COMPRESSED_EXTENSIONS) and (lower in encrypted or mentions_password):
            risky.append(name)
    return risky
