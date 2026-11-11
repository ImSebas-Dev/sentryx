"""
Sentryx v2 — Registro de actividad sospechosa.

Conecta las señales de Django y django-axes con el log de auditoría y el log de
seguridad (logger sentryx.security), para poder vigilar fuerza bruta y bloqueos.
"""
import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_login_failed
from django.dispatch import receiver

from apps.audit.utils import client_ip, log_security_event

logger = logging.getLogger(__name__)

# La verificación 2FA registra su propio evento LOGIN_FAILED con más detalle y
# además envía user_login_failed para que cuente en axes: no duplicar el registro.
SELF_LOGGED_SENDERS = {"apps.users.mfa_views"}


def _attempted_user(username):
    if not username:
        return None
    return get_user_model().objects.filter(email__iexact=username).first()


@receiver(user_login_failed)
def on_login_failed(sender, credentials=None, request=None, **kwargs):
    if sender in SELF_LOGGED_SENDERS:
        return
    from apps.alerts.pseudonymize import pseudonymize_email
    from apps.audit.models import AuditLog

    credentials = credentials or {}
    username = credentials.get("email") or credentials.get("username") or ""
    user = _attempted_user(username)
    ip = client_ip(request) if request is not None else ""
    try:
        AuditLog.log(
            AuditLog.Action.LOGIN_FAILED, "auth", user=user, ip=ip,
            resource_id=str(user.pk) if user else "",
            # Nunca la contraseña; el correo intentado va seudonimizado
            detail={"event": "password_failed", "account_exists": user is not None,
                    "username_hash": pseudonymize_email(username)},
        )
    except Exception:
        logger.exception("[Audit] No se pudo registrar el login fallido")
    log_security_event("login_failed", request, account_exists=user is not None)


def on_user_locked_out(sender, request=None, username=None, ip_address=None, **kwargs):
    from apps.alerts.pseudonymize import pseudonymize_email
    from apps.audit.models import AuditLog

    user = _attempted_user(username)
    try:
        AuditLog.log(
            AuditLog.Action.LOGIN_FAILED, "auth", user=user, ip=ip_address,
            resource_id=str(user.pk) if user else "",
            detail={"event": "account_locked",
                    "username_hash": pseudonymize_email(username or "")},
        )
    except Exception:
        logger.exception("[Audit] No se pudo registrar el bloqueo")
    log_security_event("account_locked", request, level=logging.ERROR,
                       account_exists=user is not None)


def connect():
    from axes.signals import user_locked_out
    user_locked_out.connect(on_user_locked_out, dispatch_uid="sentryx_axes_locked_out")
