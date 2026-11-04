"""
Sentryx v2 — Reglas del control de cuatro ojos.

Valida aquí, y no en la vista, todo lo que proteja la aprobación: así ninguna
tarea o endpoint futuro puede saltarse la separación de funciones.

Sobre los errores: decide() y create_request() registran el intento rechazado DESPUÉS
de salir de transaction.atomic(). Si el registro se escribe dentro y se lanza la
excepción, el rollback borra justo la evidencia que la auditoría necesita.
"""
import logging
from datetime import timedelta
from html import escape

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.alerts.risk_layers import severity_at_least
from apps.audit.models import AuditLog
from apps.four_eyes import detectors
from apps.four_eyes.models import ApprovalRequest, FourEyesPolicy
from apps.payment_shield.models import PaymentCheck
from apps.users import mfa
from apps.users.email_service import send_notification
from apps.users.organization import org_of, users_of_org

logger = logging.getLogger(__name__)

GUIDED_RESPONSE_QUESTION = "¿Ya hiciste clic o pagaste?"

PAYMENT_REASON_BY_VERDICT = {
    PaymentCheck.Verdict.ACCOUNT_MISMATCH: "pide pagar a una cuenta que no coincide con {supplier}",
    PaymentCheck.Verdict.DOMAIN_MISMATCH:
        "pide un pago desde un dominio que {supplier} no tiene autorizado",
    PaymentCheck.Verdict.LOOKALIKE_DOMAIN:
        "pide un pago desde un dominio que imita al de {supplier}",
    PaymentCheck.Verdict.UNKNOWN_SUPPLIER: "pide un pago y el remitente no es un proveedor registrado",
    PaymentCheck.Verdict.INVOICE_INCONSISTENT:
        "pide un pago con una factura que tiene datos inconsistentes",
}


class FourEyesError(Exception):
    """Regla de negocio incumplida. code es estable para el frontend y las pruebas."""

    def __init__(self, code: str, message: str, http_status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


# ── Política ──────────────────────────────────────────────
def policy_for(organization: str) -> FourEyesPolicy | None:
    """Crea la política por defecto la primera vez. Sin organización no hay política."""
    if not organization:
        return None
    policy, _ = FourEyesPolicy.objects.get_or_create(organization=organization)
    return policy


def eligible_approvers(policy: FourEyesPolicy):
    """Quienes pueden aprobar hoy: la lista de la política o, si está vacía, los admins."""
    org_users = users_of_org(policy.organization)
    selected = policy.approvers.values_list("pk", flat=True)
    if selected:
        return org_users.filter(pk__in=selected)
    return org_users.filter(role="admin")


def is_approver(policy: FourEyesPolicy, user) -> bool:
    return eligible_approvers(policy).filter(pk=user.pk).exists()


def approval_gate_open(check: PaymentCheck) -> bool:
    """Indica si el resultado 'approved' de una verificación de pago se puede aceptar."""
    policy = policy_for(check.organization)
    if policy is None or not policy.enabled:
        return True
    if check.alert_id is None:
        return False
    return ApprovalRequest.objects.filter(
        alert_id=check.alert_id, status=ApprovalRequest.Status.APPROVED).exists()


def blocks_risk_acknowledgement(check: PaymentCheck) -> bool:
    """El aviso de "Entiendo el riesgo" no sustituye una aprobación pendiente."""
    alert = check.alert
    if alert is None or not (alert.risk_signals.get("four_eyes") or {}).get("required"):
        return False
    return not ApprovalRequest.objects.filter(
        alert=alert, status=ApprovalRequest.Status.APPROVED).exists()


# ── Evaluación al analizar ────────────────────────────────
def evaluate_policy(alert, organization, payment_check, email_payload,
                    attachments=(), attachment_names=()) -> list[dict]:
    """Devuelve los motivos por los que el correo requiere aprobación (vacío si no)."""
    policy = policy_for(organization)
    if policy is None or not policy.enabled or alert is None:
        return []
    if not severity_at_least(alert.severity, policy.min_severity):
        return []

    body_text = email_payload.get("body_text", "")
    body_html = email_payload.get("body_html", "")
    reasons = []

    if policy.require_for_payment and payment_check is not None and payment_check.is_risky:
        template = PAYMENT_REASON_BY_VERDICT.get(payment_check.verdict, "pide un pago riesgoso")
        supplier = payment_check.supplier.name if payment_check.supplier else "el proveedor"
        reasons.append({"trigger": "payment", "detail": template.format(supplier=supplier)})

    if policy.require_for_credentials:
        found = detectors.detect_credential_request(body_text, body_html)
        if found:
            reasons.append({"trigger": "credentials",
                            "detail": f"pide credenciales o datos de acceso ({found[0]})"})

    if policy.require_for_attachments:
        risky = detectors.detect_risky_attachments(attachment_names, attachments,
                                                   body_text, body_html)
        if risky:
            reasons.append({"trigger": "attachments",
                            "detail": "trae adjuntos de riesgo: " + ", ".join(risky[:5])})
    return reasons


# ── Notificaciones ────────────────────────────────────────
def request_url(request_obj) -> str:
    # Enlaza siempre a la página, que exige sesión. No agregues tokens ni acciones
    # a esta URL: un prefetch del cliente de correo o un reenvío aprobarían sin querer.
    return f"{settings.FRONTEND_URL}/approvals/{request_obj.pk}"


def guided_response_url(alert_id) -> str:
    return f"{settings.FRONTEND_URL}/respond?alert={alert_id}"


def _reasons_html(request_obj) -> str:
    items = "".join(f"<li>{escape(r.get('detail', ''))}</li>" for r in request_obj.reasons)
    return f"<ul>{items}</ul>"


def _reasons_text(request_obj) -> str:
    return "\n".join(f"- {r.get('detail', '')}" for r in request_obj.reasons)


def _notify(recipients, subject, html, text):
    for email in recipients:
        send_notification(email, subject, html, text)


def notify_approvers(request_obj, policy):
    url = request_url(request_obj)
    recipients = eligible_approvers(policy).exclude(pk=request_obj.requester_id) \
        .values_list("email", flat=True)
    _notify(
        recipients, "[Sentryx] Un correo espera tu aprobación",
        f"<p>Un correo de alto riesgo quedó bloqueado y necesita una segunda revisión.</p>"
        f"{_reasons_html(request_obj)}"
        f'<p><a href="{escape(url)}">Revisar la solicitud en Sentryx</a></p>'
        f"<p>Por seguridad, este correo no aprueba nada: debes iniciar sesión.</p>",
        f"Un correo de alto riesgo necesita una segunda revisión:\n"
        f"{_reasons_text(request_obj)}\n\nRevísalo en Sentryx: {url}",
    )


def notify_requester(request_obj, decided_label):
    if request_obj.requester is None:
        return
    url = request_url(request_obj)
    guided_html = guided_text = ""
    if request_obj.status == ApprovalRequest.Status.REJECTED:
        guided = guided_response_url(request_obj.alert_id)
        guided_html = (f'<p><strong>{GUIDED_RESPONSE_QUESTION}</strong> '
                       f'<a href="{escape(guided)}">Abre la respuesta guiada</a>.</p>')
        guided_text = f"\n{GUIDED_RESPONSE_QUESTION} Abre la respuesta guiada: {guided}"
    note = (f"<p>Nota: {escape(request_obj.decision_note)}</p>"
            if request_obj.decision_note else "")
    send_notification(
        request_obj.requester.email, f"[Sentryx] Tu solicitud fue {decided_label}",
        f"<p>Tu solicitud de aprobación fue <strong>{decided_label}</strong>.</p>{note}"
        f'{guided_html}<p><a href="{escape(url)}">Ver la solicitud</a></p>',
        f"Tu solicitud de aprobación fue {decided_label}.{guided_text}\n{url}",
    )


def _audit(action, request_obj, user, ip=None, **detail):
    AuditLog.log(action=action, resource="four_eyes.request", resource_id=str(request_obj.pk),
                 user=user, ip=ip, actor="system", detail=detail)


# ── Crear solicitud ───────────────────────────────────────
def _other_approver_exists(policy, requester) -> bool:
    return eligible_approvers(policy).exclude(pk=requester.pk).exists()


NO_OTHER_APPROVER = (
    "Hace falta otra persona con permiso de aprobar: en tu organización solo tú puedes "
    "hacerlo y nadie puede aprobar su propia solicitud. Pide a un administrador que "
    "agregue otro aprobador en la política de cuatro ojos."
)


def _validate_new_request(alert, requester):
    organization = org_of(requester)
    owner = alert.owner
    if not organization or owner is None or org_of(owner) != organization:
        raise FourEyesError("other_organization",
                            "Esta alerta no pertenece a tu organización.", 403)
    if owner.pk != requester.pk and not requester.is_analyst:
        raise FourEyesError("not_allowed",
                            "Solo quien recibió el correo o un analista puede pedir la aprobación.", 403)
    signal = alert.risk_signals.get("four_eyes") or {}
    if not signal.get("required"):
        raise FourEyesError("not_required", "Este correo no requiere aprobación.", 409)
    policy = policy_for(organization)
    if not _other_approver_exists(policy, requester):
        raise FourEyesError("no_other_approver", NO_OTHER_APPROVER, 409)
    return policy, signal


def create_request(alert, requester, note="", ip=None):
    """Devuelve (solicitud, creada). Si ya hay una pendiente devuelve esa misma."""
    try:
        policy, signal = _validate_new_request(alert, requester)
    except FourEyesError as exc:
        AuditLog.log(action=AuditLog.Action.FOUR_EYES_DENIED, resource="four_eyes.request",
                     resource_id=str(alert.pk), user=requester, ip=ip,
                     detail={"attempt": "request", "reason": exc.code})
        raise

    now = timezone.now()
    with transaction.atomic():
        existing = (ApprovalRequest.objects.select_for_update()
                    .filter(alert=alert, requester=requester,
                            status=ApprovalRequest.Status.PENDING).first())
        if existing and existing.expires_at > now:
            return existing, False
        if existing:
            # Venció y la tarea aún no pasó: ciérrala para poder pedirla de nuevo
            existing.status = ApprovalRequest.Status.EXPIRED
            existing.save(update_fields=["status"])
        try:
            with transaction.atomic():
                request_obj = ApprovalRequest.objects.create(
                    alert=alert, requester=requester, organization=org_of(requester),
                    payment_check=alert.payment_checks.first(),
                    reasons=signal.get("reasons", []), requester_note=note,
                    expires_at=now + timedelta(minutes=policy.expiry_minutes),
                )
        except IntegrityError:
            # Dos clics simultáneos: la restricción única dejó pasar solo uno
            return ApprovalRequest.objects.get(
                alert=alert, requester=requester, status=ApprovalRequest.Status.PENDING), False

    _audit(AuditLog.Action.FOUR_EYES_REQUESTED, request_obj, requester, ip)
    notify_approvers(request_obj, policy)
    return request_obj, True


# ── Decidir ───────────────────────────────────────────────
def _decision_error(request_obj, policy, actor, approve, totp_code, note):
    """Devuelve el error que impide decidir, o None. Conserva este orden de validación."""
    if not org_of(actor) or org_of(actor) != request_obj.organization:
        return FourEyesError("other_organization",
                             "Esta solicitud pertenece a otra organización.", 403)
    if request_obj.requester_id == actor.pk:
        if not _other_approver_exists(policy, actor):
            return FourEyesError("no_other_approver", NO_OTHER_APPROVER, 403)
        return FourEyesError("self_approval", "No puedes decidir tu propia solicitud.", 403)
    if not is_approver(policy, actor):
        return FourEyesError("not_approver", "No tienes permiso para decidir esta solicitud.", 403)
    if request_obj.status != ApprovalRequest.Status.PENDING:
        return FourEyesError("already_decided",
                             f"Esta solicitud ya está {request_obj.get_status_display().lower()}.", 409)
    if not approve and not (note or "").strip():
        return FourEyesError("note_required", "Escribe el motivo del rechazo.", 400)
    # Valida el código de último: si el resto falla no se gasta un TOTP válido
    if policy.require_mfa_for_approval:
        if not actor.mfa_enabled:
            return FourEyesError(
                "mfa_required",
                "Activa la verificación en dos pasos en Seguridad de la cuenta para poder aprobar.",
                403)
        try:
            if not mfa.verify_totp(actor, totp_code):
                return FourEyesError("invalid_totp",
                                     "El código no es válido o ya se usó. Espera al siguiente.", 400)
        except mfa.MFAConfigurationError as exc:
            return FourEyesError("mfa_not_configured", str(exc), 503)
    return None


def decide(pk, actor, approve: bool, totp_code="", note="", ip=None) -> ApprovalRequest:
    """Aprueba o rechaza una solicitud. Bloquea la fila para evitar dos decisiones."""
    failure = None
    expired_now = False
    with transaction.atomic():
        request_obj = ApprovalRequest.objects.select_for_update().get(pk=pk)
        policy = policy_for(request_obj.organization)
        is_stale = (request_obj.status == ApprovalRequest.Status.PENDING
                    and request_obj.expires_at <= timezone.now())
        same_org = org_of(actor) == request_obj.organization
        if is_stale and same_org:
            request_obj.status = ApprovalRequest.Status.EXPIRED
            request_obj.save(update_fields=["status"])
            expired_now = True
            failure = FourEyesError("expired", "Esta solicitud ya venció.", 409)
        else:
            failure = _decision_error(request_obj, policy, actor, approve, totp_code, note)
        if failure is None:
            request_obj.status = (ApprovalRequest.Status.APPROVED if approve
                                  else ApprovalRequest.Status.REJECTED)
            request_obj.decided_by = actor
            request_obj.decided_at = timezone.now()
            request_obj.decision_note = (note or "").strip()
            request_obj.save(update_fields=["status", "decided_by", "decided_at",
                                            "decision_note"])

    # Registra aquí, fuera del bloque atómico, para que el intento quede guardado
    if failure is not None:
        _audit(AuditLog.Action.FOUR_EYES_DENIED, request_obj, actor, ip,
               attempt="approve" if approve else "reject", reason=failure.code)
        if expired_now:
            _finish_expiration(request_obj)
        raise failure

    action = AuditLog.Action.FOUR_EYES_APPROVED if approve else AuditLog.Action.FOUR_EYES_REJECTED
    _audit(action, request_obj, actor, ip)
    notify_requester(request_obj, "aprobada" if approve else "rechazada")
    return request_obj


def cancel(pk, actor, ip=None) -> ApprovalRequest:
    failure = None
    with transaction.atomic():
        request_obj = ApprovalRequest.objects.select_for_update().get(pk=pk)
        if request_obj.requester_id != actor.pk:
            failure = FourEyesError("not_allowed", "Solo quien pidió la aprobación puede cancelarla.", 403)
        elif request_obj.status != ApprovalRequest.Status.PENDING:
            failure = FourEyesError("already_decided", "Esta solicitud ya no está pendiente.", 409)
        else:
            request_obj.status = ApprovalRequest.Status.CANCELLED
            request_obj.save(update_fields=["status"])
    if failure is not None:
        _audit(AuditLog.Action.FOUR_EYES_DENIED, request_obj, actor, ip,
               attempt="cancel", reason=failure.code)
        raise failure
    _audit(AuditLog.Action.FOUR_EYES_CANCELLED, request_obj, actor, ip)
    return request_obj


# ── Vencimiento ───────────────────────────────────────────
def _finish_expiration(request_obj):
    _audit(AuditLog.Action.FOUR_EYES_EXPIRED, request_obj, None)
    notify_requester(request_obj, "vencida")
    admins = users_of_org(request_obj.organization).filter(role="admin") \
        .values_list("email", flat=True)
    url = request_url(request_obj)
    _notify(
        admins, "[Sentryx] Una solicitud de aprobación venció sin respuesta",
        f"<p>Nadie decidió esta solicitud a tiempo y el correo sigue bloqueado.</p>"
        f'{_reasons_html(request_obj)}<p><a href="{escape(url)}">Ver la solicitud</a></p>',
        f"Una solicitud venció sin respuesta:\n{_reasons_text(request_obj)}\n{url}",
    )


def expire_overdue() -> int:
    """Pasa a expired las solicitudes vencidas, avisa al solicitante y escala a los admins."""
    expired = []
    overdue = ApprovalRequest.objects.filter(
        status=ApprovalRequest.Status.PENDING, expires_at__lte=timezone.now(),
    ).values_list("pk", flat=True)
    for pk in overdue:
        with transaction.atomic():
            # Vuelve a comprobar con la fila bloqueada: pudieron decidirla en este instante
            request_obj = (ApprovalRequest.objects.select_for_update(skip_locked=True)
                           .filter(pk=pk, status=ApprovalRequest.Status.PENDING).first())
            if request_obj is None:
                continue
            request_obj.status = ApprovalRequest.Status.EXPIRED
            request_obj.save(update_fields=["status"])
        expired.append(request_obj)
    for request_obj in expired:
        _finish_expiration(request_obj)
    return len(expired)
