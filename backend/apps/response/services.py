"""Sentryx v2 — Lógica de la respuesta guiada."""
import logging
from html import escape

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.incidents.models import Incident, IncidentTimeline
from apps.response.models import EmergencyContact, ResponseSession
from apps.users.email_service import send_notification
from apps.users.organization import org_of, same_org, users_of_org

logger = logging.getLogger(__name__)

# Déjalos sin teléfono: el admin debe completarlos con los números que verifique.
# No escribas aquí números de bancos ni de autoridades: pueden cambiar o estar mal.
PLACEHOLDER_CONTACTS = [
    ("Línea de fraude de tu banco (complétala)", EmergencyContact.Kind.BANK),
    ("Responsable de sistemas o gerencia (complétalo)", EmergencyContact.Kind.INTERNAL),
    ("Responsable del tratamiento de datos (complétalo)", EmergencyContact.Kind.INTERNAL),
]
CONTACT_WARNING = "Verifica estos números con tu banco antes de necesitarlos."


def contacts_for(organization: str):
    """Crea los contactos de ejemplo la primera vez que se consulta la organización."""
    if not organization:
        return EmergencyContact.objects.none()
    contacts = EmergencyContact.objects.filter(organization=organization)
    if not contacts.exists():
        EmergencyContact.objects.bulk_create([
            EmergencyContact(organization=organization, name=name, kind=kind)
            for name, kind in PLACEHOLDER_CONTACTS
        ])
    return contacts


def can_access_session(user, session) -> bool:
    if session.user_id == user.pk:
        return True
    return user.is_admin and same_org(user, session.user) if session.user else False


def alert_for_user(user, alert_id):
    """Solo se vincula una alerta propia o, para el admin, una de su organización."""
    from apps.alerts.models import Alert
    alert = Alert.objects.select_related("owner").filter(pk=alert_id).first()
    if alert is None:
        return None
    if alert.owner_id == user.pk or (user.is_admin and alert.owner and same_org(user, alert.owner)):
        return alert
    return None


def _notify_admins(session):
    url = f"{settings.FRONTEND_URL}/incidents"
    who = session.user.username if session.user else "Un usuario"
    admins = users_of_org(session.organization).filter(role="admin") \
        .exclude(pk=session.user_id).values_list("email", flat=True)
    title = session.playbook.title
    for email in admins:
        send_notification(
            email, "[Sentryx] Alguien de tu empresa cayó en un phishing",
            f"<p><strong>{escape(who)}</strong> inició la respuesta guiada: "
            f"«{escape(title)}».</p><p>Comunícate con esta persona cuanto antes.</p>"
            f'<p><a href="{escape(url)}">Ver incidentes en Sentryx</a></p>',
            f"{who} inició la respuesta guiada: {title}. Revisa los incidentes: {url}",
        )


def start_session(user, playbook, alert=None, answers=None, ip=None) -> ResponseSession:
    with transaction.atomic():
        incident = Incident.objects.create(
            title=f"Respuesta guiada: {playbook.title}",
            description=playbook.description,
            severity=playbook.severity,
            created_by=user,
            mitre_technique=alert.mitre_technique if alert else "",
        )
        if alert is not None:
            incident.alerts.add(alert)
        session = ResponseSession.objects.create(
            user=user, organization=org_of(user), alert=alert, playbook=playbook,
            incident=incident, answers=answers or {},
        )
        IncidentTimeline.objects.create(
            incident=incident, event_type="guided_response",
            description="Respuesta guiada iniciada", actor=user,
        )
    AuditLog.log(action=AuditLog.Action.RESPONSE_STARTED, resource="response.session",
                 resource_id=str(session.pk), user=user, ip=ip,
                 detail={"playbook": playbook.key, "alert": str(alert.pk) if alert else None})
    _notify_admins(session)
    return session


def mark_step(session, step_id, done, note, user, ip=None) -> ResponseSession:
    step = next(s for s in session.playbook.steps if s["id"] == step_id)
    now = timezone.now()
    with transaction.atomic():
        locked = ResponseSession.objects.select_for_update().get(pk=session.pk)
        state = dict(locked.steps_state)
        state[step_id] = {"done": done, "done_at": now.isoformat() if done else None, "note": note}
        locked.steps_state = state
        locked.save(update_fields=["steps_state"])
        if locked.incident_id:
            verb = "completado" if done else "marcado como pendiente"
            IncidentTimeline.objects.create(
                incident_id=locked.incident_id, event_type="guided_step",
                description=f"Paso {verb}: {step['title']}", actor=user,
            )
    AuditLog.log(action=AuditLog.Action.RESPONSE_STEP, resource="response.session",
                 resource_id=str(session.pk), user=user, ip=ip,
                 detail={"step": step_id, "done": done})
    return locked


def complete_session(session, user, ip=None) -> ResponseSession:
    session.status = ResponseSession.Status.COMPLETED
    session.completed_at = timezone.now()
    session.save(update_fields=["status", "completed_at"])
    if session.incident_id:
        IncidentTimeline.objects.create(
            incident_id=session.incident_id, event_type="guided_response",
            description="Respuesta guiada terminada", actor=user,
        )
    AuditLog.log(action=AuditLog.Action.RESPONSE_COMPLETED, resource="response.session",
                 resource_id=str(session.pk), user=user, ip=ip)
    return session
