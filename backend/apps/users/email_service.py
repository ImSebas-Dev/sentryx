"""
Sentryx v2 — Servicio de correo transaccional via SendGrid.
Gestiona verificación de cuenta y recuperación de contraseña.
"""
import logging
from html import escape
from urllib.parse import urlencode

from django.conf import settings

logger = logging.getLogger(__name__)


def _send(to_email: str, subject: str, html_body: str, text_body: str = "") -> bool:
    """Envía un correo via SendGrid API v3."""
    try:
        import httpx
        payload = {
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {
                "email": settings.SENDGRID_FROM_EMAIL,
                "name":  "Sentryx",
            },
            "subject": subject,
            "content": [
                {"type": "text/plain", "value": text_body or subject},
                {"type": "text/html",  "value": html_body},
            ],
        }
        resp = httpx.post(
            "https://api.sendgrid.com/v3/mail/send",
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
                "Content-Type":  "application/json",
            },
            timeout=10.0,
        )
        if resp.status_code not in (200, 202):
            # Sin el cuerpo de la respuesta: puede repetir datos de la petición
            logger.error(f"[Email] SendGrid respondió {resp.status_code}")
            return False
        logger.info(f"[Email] Correo enviado: {subject}")
        return True
    except Exception as e:
        logger.error(f"[Email] Error enviando correo: {type(e).__name__}")
        return False


def send_notification(to_email: str, subject: str, html_body: str, text_body: str = "") -> bool:
    """
    Aviso interno de las funciones de seguridad. Sin SENDGRID_API_KEY solo deja el
    registro en el log, para que ninguna función dependa de tener correo configurado.
    Nunca pongas en el cuerpo el contenido del correo sospechoso.
    """
    if not settings.SENDGRID_API_KEY:
        logger.info(f"[Email] Sin SENDGRID_API_KEY; aviso no enviado: {subject}")
        return False
    wrapped = (
        '<div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;'
        'background:#0f1117;color:#e5e7eb;padding:32px;border-radius:12px">'
        '<div style="font-size:22px;font-weight:800;color:#60a5fa;margin-bottom:16px">'
        f"🛡 Sentryx</div>{html_body}</div>"
    )
    return _send(to_email, subject, wrapped, text_body)


def _base_url() -> str:
    return getattr(settings, "FRONTEND_URL", "http://localhost").rstrip("/")


def _link(path: str, **params) -> str:
    """Enlace al frontend con los parámetros codificados (el correo podría traer caracteres raros)."""
    return f"{_base_url()}{path}?{urlencode(params)}"


def send_verification_email(user) -> bool:
    """Envía el correo de verificación de cuenta después del registro."""
    token = user.rotate_verification_token()
    url   = _link("/verify-email", token=token, email=user.email)
    hours = settings.EMAIL_VERIFICATION_TIMEOUT_HOURS

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;background:#0f1117;
                color:#e5e7eb;padding:32px;border-radius:12px">
      <div style="text-align:center;margin-bottom:24px">
        <span style="font-size:28px;font-weight:800;color:#60a5fa">🛡 Sentryx</span>
      </div>
      <h2 style="color:#f9fafb;margin-bottom:8px">Verifica tu correo electrónico</h2>
      <p style="color:#9ca3af;margin-bottom:24px">
        Gracias por registrarte en Sentryx. Haz clic en el botón para confirmar
        tu dirección de correo. El enlace es válido por <strong>{hours} horas</strong>
        y solo se puede usar una vez.
      </p>
      <div style="text-align:center;margin-bottom:24px">
        <a href="{escape(url)}"
           style="background:#2563eb;color:#fff;padding:12px 32px;border-radius:8px;
                  text-decoration:none;font-weight:600;display:inline-block">
          Verificar correo
        </a>
      </div>
      <p style="color:#6b7280;font-size:12px">
        Si no creaste una cuenta en Sentryx, ignora este mensaje.<br>
        Una vez verificado tu correo, ya puedes iniciar sesión.
      </p>
      <hr style="border-color:#1f2937;margin:24px 0">
      <p style="color:#4b5563;font-size:11px;text-align:center">
        Sentryx · Plataforma de detección de phishing ·
        <a href="{escape(_base_url())}/privacy" style="color:#6b7280">Política de privacidad</a>
      </p>
    </div>
    """
    return _send(user.email, "Verifica tu correo — Sentryx", html,
                 f"Verifica tu correo en Sentryx: {url}")


def send_password_reset_email(user) -> bool:
    """Envía el enlace de recuperación de contraseña."""
    token = user.rotate_reset_token()
    url   = _link("/reset-password", token=token, email=user.email)
    minutes = settings.PASSWORD_RESET_TIMEOUT_MINUTES
    html  = f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;background:#0f1117;
                color:#e5e7eb;padding:32px;border-radius:12px">
      <div style="text-align:center;margin-bottom:24px">
        <span style="font-size:28px;font-weight:800;color:#60a5fa">🛡 Sentryx</span>
      </div>
      <h2 style="color:#f9fafb;margin-bottom:8px">Recupera tu contraseña</h2>
      <p style="color:#9ca3af;margin-bottom:24px">
        Recibimos una solicitud para restablecer la contraseña de tu cuenta.
        El enlace es válido por <strong>{minutes} minutos</strong> y solo se puede usar una vez.
      </p>
      <div style="text-align:center;margin-bottom:24px">
        <a href="{escape(url)}"
           style="background:#2563eb;color:#fff;padding:12px 32px;border-radius:8px;
                  text-decoration:none;font-weight:600;display:inline-block">
          Restablecer contraseña
        </a>
      </div>
      <p style="color:#6b7280;font-size:12px">
        Si no solicitaste este cambio, ignora este correo.
        Tu contraseña actual sigue siendo segura.
      </p>
    </div>
    """
    return _send(user.email, "Recupera tu contraseña — Sentryx", html,
                 f"Restablece tu contraseña: {url}")
