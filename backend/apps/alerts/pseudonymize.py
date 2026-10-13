"""
Sentryx v2 — Servicio de seudonimización.
Centraliza el hashing SHA-256 + salt para cumplir Ley 1581/2012.
Todos los datos personales (emails, IPs) pasan por aquí antes de almacenarse.
"""
import hashlib
import re
from django.conf import settings


def _hash(value: str) -> str:
    """SHA-256 del valor + salt del despliegue."""
    salt = settings.PSEUDONYMIZATION_SALT
    return hashlib.sha256(f"{value.lower().strip()}{salt}".encode()).hexdigest()


def pseudonymize_email(email: str) -> str:
    """Hash del email completo. Nunca almacenar el email en texto plano."""
    if not email:
        return ""
    return _hash(email)


def pseudonymize_ip(ip: str) -> str:
    """Hash de la dirección IP."""
    if not ip:
        return ""
    return _hash(ip)


def pseudonymize_subject(subject: str) -> str:
    """Hash del asunto del correo."""
    if not subject:
        return ""
    return _hash(subject)


def pseudonymize_text(text: str) -> str:
    """Hash del cuerpo del correo. Sirve solo para reconocer correos idénticos."""
    if not text:
        return ""
    return _hash(text)


def extract_domain(email_or_header: str) -> str:
    """
    Extrae solo el dominio de una dirección de correo.
    El dominio no es dato personal — es seguro almacenarlo.
    Ej: 'Evil Corp <attacker@evil.tk>' → 'evil.tk'
    """
    match = re.search(r"@([\w.\-]+)", email_or_header.lower())
    return match.group(1) if match else ""


def safe_truncate_url(url: str, max_len: int = 80) -> str:
    """
    Trunca una URL para almacenamiento, eliminando parámetros de query
    que podrían contener tokens o datos de usuario.
    """
    # Eliminar query string (puede contener tokens personales)
    base = url.split("?")[0].split("#")[0]
    return base[:max_len]
