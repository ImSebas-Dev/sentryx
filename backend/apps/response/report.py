"""
Sentryx v2 — Paquete de denuncia en PDF.

Conserva el estilo de los informes de apps/alerts/reports.py. Reglas al editarlo:
  - Desactiva siempre las URL y dominios con defang(): el PDF se reenvía a terceros
    y un enlace activo a un sitio de phishing es un riesgo.
  - Pasa todo texto del usuario por _safe(): reportlab interpreta sus marcas XML y
    Helvetica solo tiene Latin-1.
  - No incluyas remitente, destinatario, asunto ni cuerpo (Ley 1581/2012): solo
    dominios, hashes y metadatos.
"""
import io
import re
from xml.sax.saxutils import escape

from django.conf import settings
from django.utils import timezone

LEGAL_NOTE = "Verifique los plazos y requisitos vigentes con la normativa y con su asesor legal."
CAI_FALLBACK = ("Busque el CAI Virtual en el sitio oficial de la Policía Nacional de Colombia "
                "y siga las instrucciones para presentar la denuncia.")


def defang(value: str) -> str:
    """Convierte http://ejemplo.com en hxxp://ejemplo[.]com para que no sea clicable."""
    value = re.sub(r"^http", "hxxp", value or "", flags=re.IGNORECASE)
    return value.replace(".", "[.]")


def _latin1(text) -> str:
    return str(text or "").encode("latin-1", "replace").decode("latin-1")


def _safe(text) -> str:
    return escape(_latin1(text))


def _fmt(moment) -> str:
    return timezone.localtime(moment).strftime("%d/%m/%Y %H:%M") if moment else "-"


def collect_iocs(alert) -> list[tuple[str, str]]:
    if alert is None:
        return []
    iocs = []
    if alert.sender_domain:
        iocs.append(("Dominio del remitente", defang(alert.sender_domain)))
    for item in alert.suspicious_urls or []:
        url = item.get("url") if isinstance(item, dict) else item
        if url:
            iocs.append(("URL sospechosa", defang(url)))
    return iocs


def render_pdf(session) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    NAVY   = colors.HexColor("#0f1e4a")
    GRAY   = colors.HexColor("#6b7280")
    LIGHT  = colors.HexColor("#f3f4f6")
    BORDER = colors.HexColor("#d1d5db")

    base  = getSampleStyleSheet()
    title = ParagraphStyle("t", parent=base["Title"], fontSize=18, textColor=NAVY,
                           spaceAfter=4, alignment=0)
    sub   = ParagraphStyle("s", parent=base["Normal"], fontSize=10, textColor=GRAY)
    h2    = ParagraphStyle("h2", parent=base["Heading2"], fontSize=12.5, textColor=NAVY,
                           spaceBefore=14, spaceAfter=6, keepWithNext=1)
    body  = ParagraphStyle("b", parent=base["Normal"], fontSize=9.5, leading=14)
    cell  = ParagraphStyle("c", parent=base["Normal"], fontSize=8.5, leading=11)
    note  = ParagraphStyle("n", parent=base["Normal"], fontSize=8, leading=11, textColor=GRAY)

    def table(rows, widths):
        wrapped = [[Paragraph(_safe(c), cell) if i else c for c in row]
                   for i, row in enumerate(rows)]
        result = Table(wrapped, colWidths=widths, repeatRows=1)
        result.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8.5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
            ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        return result

    alert, playbook = session.alert, session.playbook
    who = session.user.username if session.user else "usuario eliminado"
    story = [
        Paragraph("Paquete de denuncia", title),
        Paragraph(_safe(f"Respuesta guiada: {playbook.title}"), sub),
        Spacer(1, 8),
    ]

    # ── Resumen de hechos ─────────────────────────────────
    story.append(Paragraph("1. Resumen de hechos", h2))
    facts = [
        f"<b>Qué pasó:</b> {_safe(playbook.title)}.",
        f"<b>Organización:</b> {_safe(session.organization or 'Sin organización')}.",
        f"<b>Reportó:</b> {_safe(who)}.",
        f"<b>Inicio de la respuesta:</b> {_fmt(session.started_at)} (hora de Colombia).",
        f"<b>Estado:</b> {_safe(session.get_status_display())}.",
    ]
    for answer_key, answer in (session.answers or {}).items():
        if isinstance(answer, (str, int, float)):
            facts.append(f"<b>{_safe(answer_key)}:</b> {_safe(answer)}.")
    story.extend(Paragraph(fact, body) for fact in facts)

    # ── Línea de tiempo ───────────────────────────────────
    story.append(Paragraph("2. Línea de tiempo", h2))
    rows = [["Hora", "Evento"]]
    if session.incident_id:
        for event in session.incident.timeline.all():
            rows.append([_fmt(event.occurred_at), event.description])
    story.append(table(rows, [3.2 * cm, 13.8 * cm]))

    notes = [(step["title"], session.steps_state.get(step["id"], {}).get("note"))
             for step in playbook.steps]
    notes = [(t, n) for t, n in notes if n]
    if notes:
        story.append(Spacer(1, 6))
        story.append(table([["Paso", "Nota del usuario"], *notes], [6 * cm, 11 * cm]))

    # ── IOC ───────────────────────────────────────────────
    story.append(Paragraph("3. Indicadores de compromiso (IOCs)", h2))
    iocs = collect_iocs(alert)
    if iocs:
        story.append(table([["Tipo", "Valor (desactivado)"], *iocs], [5 * cm, 12 * cm]))
        story.append(Paragraph(
            "Los enlaces se muestran desactivados a propósito. No los abra.", note))
    else:
        story.append(Paragraph("No hay un correo analizado vinculado a esta respuesta.", body))

    # ── Análisis ──────────────────────────────────────────
    story.append(Paragraph("4. Análisis técnico y evidencia", h2))
    if alert is not None:
        story.append(Paragraph(
            f"<b>Score de riesgo:</b> {alert.risk_score:.0f}/100 &nbsp;|&nbsp; "
            f"<b>Técnica MITRE ATT&amp;CK:</b> {_safe(alert.mitre_technique or 'T1566')} &nbsp;|&nbsp; "
            f"<b>Severidad:</b> {_safe(alert.severity)}", body))
        hashes = [("Cuerpo del correo", alert.email_body_hash), ("Remitente", alert.sender_hash),
                  ("Asunto", alert.subject_hash)]
        hashes = [(label, value) for label, value in hashes if value]
        if hashes:
            story.append(Spacer(1, 6))
            story.append(table([["Evidencia", "Hash SHA-256 (con salt de esta instalación)"], *hashes],
                               [4 * cm, 13 * cm]))
    else:
        story.append(Paragraph("Sin alerta vinculada: no hay score ni hash de evidencia.", body))

    # ── Próximos pasos ────────────────────────────────────
    story.append(Paragraph("5. Próximos pasos", h2))
    cai_url = settings.CAI_VIRTUAL_URL
    cai_text = (f"Presente la denuncia en el CAI Virtual de la Policía Nacional: {defang(cai_url)} "
                "(escriba la dirección en el navegador)." if cai_url else CAI_FALLBACK)
    steps = [
        f"<b>Denuncia:</b> {_safe(cai_text)} Adjunte este documento. Sentryx no envía nada "
        "automáticamente.",
        "<b>Superintendencia de Industria y Comercio (SIC):</b> si se comprometieron datos "
        "personales de clientes o empleados, evalúe con el responsable del tratamiento el reporte "
        "del incidente de seguridad ante la SIC.",
        "<b>Banco:</b> si hubo una transferencia, solicite por escrito la reversión y conserve el "
        "número de radicado.",
    ]
    story.extend(Paragraph(step, body) for step in steps)
    story.append(Spacer(1, 8))
    story.append(Paragraph(_safe(LEGAL_NOTE), note))
    story.append(Paragraph(_safe(f"Generado por Sentryx el {_fmt(timezone.now())}."), note))

    buffer = io.BytesIO()
    # Deja el PDF sin comprimir: pesa poco y permite comprobar su texto en las pruebas
    doc = SimpleDocTemplate(buffer, pagesize=A4, title="Paquete de denuncia", author="Sentryx",
                            leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=1.8 * cm, bottomMargin=1.8 * cm, pageCompression=0)
    doc.build(story)
    return buffer.getvalue()
