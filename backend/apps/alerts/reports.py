"""
Sentryx v2 — Generación de informes semanales y mensuales.

Este módulo hace tres cosas:
  1. Calcula el rango de fechas del periodo pedido (semana o mes calendario).
  2. Reúne las métricas de las alertas e incidentes del usuario en ese rango.
  3. Exporta esas métricas a PDF (informe formal) o CSV (datos para Excel).

Reglas que se deben respetar al modificar este archivo:
  - Recibir siempre el queryset YA filtrado por usuario desde la vista.
    Aquí no se decide quién ve qué; eso lo hace _alert_queryset() en views.py.
  - No incluir nunca datos personales: ni remitentes, ni destinatarios,
    ni asuntos. Solo dominios y metadatos (Ley 1581/2012).
  - Usar solo caracteres Latin-1 en el PDF: la fuente Helvetica de
    ReportLab no tiene símbolos como ≥ o emojis y los pintaría como cuadros.
"""
import csv
import io
from calendar import monthrange
from datetime import datetime, time, timedelta

from django.db.models import Avg, Count, Max, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun",
                "jul", "ago", "sep", "oct", "nov", "dic"]

SEVERITY_LABELS = {"CRITICAL": "Crítica", "HIGH": "Alta", "MEDIUM": "Media", "LOW": "Baja"}
SEVERITY_ORDER  = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]

STATUS_LABELS = {
    "new": "Nueva", "acknowledged": "En revisión",
    "resolved": "Resuelta", "false_pos": "Falso positivo",
}
TYPE_LABELS = {
    "bec": "BEC", "whaling": "Whaling", "spear": "Spear phishing",
    "clone": "Clone phishing", "vishing": "Vishing", "smishing": "Smishing",
    "generic": "Genérico", "unknown": "Sin clasificar",
}
INCIDENT_STATUS_LABELS = {
    "new": "Nuevo", "investigating": "En investigación",
    "contained": "Contenido", "closed": "Cerrado",
}

MAX_WEEKLY_OFFSET  = 52   # hasta un año hacia atrás
MAX_MONTHLY_OFFSET = 24   # hasta dos años hacia atrás
MAX_PDF_ROWS       = 500  # el CSV lleva todas las filas; el PDF se recorta para no pesar demasiado


# ══════════════════════════════════════════════════════════
#  1. Periodos
# ══════════════════════════════════════════════════════════

def _fmt_date(d, with_year=True):
    """Formatear una fecha como '28 sep 2026' sin depender del locale del sistema."""
    base = f"{d.day} {MESES_CORTOS[d.month - 1]}"
    return f"{base} {d.year}" if with_year else base


def period_range(period: str, offset: int = 0):
    """
    Calcular el rango [inicio, fin) del periodo en la zona horaria local.

    period  'weekly'  -> semana calendario de lunes a domingo
            'monthly' -> mes calendario completo
    offset  0 = periodo actual, 1 = anterior, 2 = dos atrás, ...

    Devuelve un dict con start/end (datetime con zona), las fechas
    inclusivas para mostrar, la etiqueta legible y si el periodo sigue en curso.
    """
    tz    = timezone.get_current_timezone()
    today = timezone.localdate()

    if period == "weekly":
        start_date = today - timedelta(days=today.weekday()) - timedelta(weeks=offset)
        end_date   = start_date + timedelta(days=7)
        last_day   = end_date - timedelta(days=1)
        same_year  = start_date.year == last_day.year
        label = (f"Semana del {_fmt_date(start_date, with_year=not same_year)} "
                 f"al {_fmt_date(last_day)}")
    elif period == "monthly":
        year, month = today.year, today.month - offset
        while month <= 0:
            month += 12
            year  -= 1
        start_date = today.replace(year=year, month=month, day=1)
        days       = monthrange(year, month)[1]
        end_date   = start_date + timedelta(days=days)
        last_day   = end_date - timedelta(days=1)
        label = f"{MESES[month - 1].capitalize()} de {year}"
    else:
        raise ValueError("El periodo debe ser 'weekly' o 'monthly'.")

    start = timezone.make_aware(datetime.combine(start_date, time.min), tz)
    end   = timezone.make_aware(datetime.combine(end_date,   time.min), tz)

    return {
        "period":      period,
        "offset":      offset,
        "start":       start,
        "end":         end,
        "start_date":  start_date,
        "last_date":   last_day,
        "label":       label,
        "in_progress": offset == 0,
    }


def period_options(period: str, count: int = 12):
    """Lista de periodos disponibles para el selector del frontend."""
    limit = MAX_WEEKLY_OFFSET if period == "weekly" else MAX_MONTHLY_OFFSET
    options = []
    for offset in range(min(count, limit + 1)):
        r = period_range(period, offset)
        options.append({
            "offset":      offset,
            "label":       r["label"],
            "start":       r["start_date"].isoformat(),
            "end":         r["last_date"].isoformat(),
            "in_progress": r["in_progress"],
        })
    return options


# ══════════════════════════════════════════════════════════
#  2. Métricas
# ══════════════════════════════════════════════════════════

def build_report_data(user, alert_qs, incident_qs, period: str, offset: int):
    """
    Reunir todas las métricas del informe.

    alert_qs     queryset de alertas YA filtrado por usuario (sin filtro de fechas)
    incident_qs  queryset de incidentes YA filtrado por usuario (sin filtro de fechas)
    """
    rng = period_range(period, offset)
    qs  = alert_qs.filter(detected_at__gte=rng["start"], detected_at__lt=rng["end"])

    total = qs.count()
    agg   = qs.aggregate(avg=Avg("risk_score"), max=Max("risk_score"))

    by_severity = {k: 0 for k in SEVERITY_ORDER}
    for row in qs.values("severity").annotate(c=Count("id")):
        by_severity[row["severity"]] = row["c"]

    by_type = {row["phishing_type"]: row["c"] for row in
               qs.values("phishing_type").annotate(c=Count("id")).order_by("-c")}

    by_status = {k: 0 for k in STATUS_LABELS}
    for row in qs.values("status").annotate(c=Count("id")):
        by_status[row["status"]] = row["c"]

    # Serie diaria completa (los días sin alertas también aparecen con 0)
    counts_by_day = {
        row["day"]: row["c"] for row in
        qs.annotate(day=TruncDate("detected_at", tzinfo=timezone.get_current_timezone()))
          .values("day").annotate(c=Count("id"))
    }
    daily, d = [], rng["start_date"]
    while d <= rng["last_date"]:
        daily.append({"date": d, "count": counts_by_day.get(d, 0)})
        d += timedelta(days=1)

    top_domains = list(
        qs.exclude(sender_domain="")
          .values("sender_domain").annotate(c=Count("id")).order_by("-c")[:5]
    )
    top_mitre = list(
        qs.exclude(mitre_technique="")
          .values("mitre_technique").annotate(c=Count("id")).order_by("-c")[:5]
    )
    campaigns = list(
        qs.exclude(campaign__isnull=True)
          .values("campaign__name").annotate(c=Count("id")).order_by("-c")[:5]
    )

    # Comparación con el periodo inmediatamente anterior
    prev = period_range(period, offset + 1)
    prev_total = alert_qs.filter(
        detected_at__gte=prev["start"], detected_at__lt=prev["end"]
    ).count()
    change_pct = None
    if prev_total:
        change_pct = round((total - prev_total) / prev_total * 100, 1)

    reviewed = by_status["resolved"] + by_status["false_pos"] + by_status["acknowledged"]

    incidents = incident_qs.filter(created_at__gte=rng["start"], created_at__lt=rng["end"])
    inc_by_status = {row["status"]: row["c"] for row in
                     incidents.values("status").annotate(c=Count("id"))}

    alerts = list(
        qs.order_by("-detected_at").values(
            "detected_at", "title", "severity", "phishing_type", "risk_score",
            "score_headers", "score_content", "score_urls", "status",
            "sender_domain", "mitre_technique", "campaign__name",
            "url_count", "has_attachments",
        )
    )

    return {
        "user": {
            "email":        user.email,
            "role":         user.get_role_display() if hasattr(user, "get_role_display") else user.role,
            "organization": getattr(user, "organization", "") or "",
            "is_admin":     getattr(user, "is_admin", False),
        },
        "period":       rng,
        "generated_at": timezone.localtime(),
        "summary": {
            "total":          total,
            "critical":       by_severity["CRITICAL"],
            "high":           by_severity["HIGH"],
            "avg_score":      round(agg["avg"] or 0, 1),
            "max_score":      round(agg["max"] or 0, 1),
            "false_pos":      by_status["false_pos"],
            "fp_rate":        round(by_status["false_pos"] / total * 100, 1) if total else 0,
            "review_rate":    round(reviewed / total * 100, 1) if total else 0,
            "pending":        by_status["new"],
            "prev_total":     prev_total,
            "prev_label":     prev["label"],
            "change_pct":     change_pct,
            "campaign_count": len(campaigns),
            "incident_count": incidents.count(),
        },
        "by_severity":   by_severity,
        "by_type":       by_type,
        "by_status":     by_status,
        "daily":         daily,
        "top_domains":   top_domains,
        "top_mitre":     top_mitre,
        "campaigns":     campaigns,
        "incidents": {
            "by_status": inc_by_status,
            "items": list(incidents.order_by("-created_at").values(
                "title", "severity", "status", "created_at", "closed_at",
            )[:50]),
        },
        "alerts": alerts,
    }


def build_preview(data):
    """Versión ligera de los datos para la vista previa del frontend (JSON)."""
    p = data["period"]
    return {
        "label":       p["label"],
        "start":       p["start_date"].isoformat(),
        "end":         p["last_date"].isoformat(),
        "in_progress": p["in_progress"],
        "summary":     data["summary"],
        "by_severity": data["by_severity"],
        "by_type":     data["by_type"],
        "by_status":   data["by_status"],
        "daily":       [{"date": d["date"].isoformat(), "count": d["count"]} for d in data["daily"]],
        "top_domains": data["top_domains"],
        "scope":       "all" if data["user"]["is_admin"] else "mine",
    }


def build_executive_text(data):
    """Redactar el párrafo de resumen ejecutivo a partir de las métricas."""
    s, period = data["summary"], data["period"]
    tipo = "semana" if period["period"] == "weekly" else "mes"

    if s["total"] == 0:
        return (f"Durante este {tipo} no se registraron correos sospechosos ni de phishing. "
                f"No hay alertas pendientes de revisión para el periodo.")

    parts = [f"Durante este {tipo} se detectaron <b>{s['total']}</b> "
             f"correo{'s' if s['total'] != 1 else ''} sospechoso{'s' if s['total'] != 1 else ''} "
             f"o de phishing, con un score de riesgo promedio de <b>{s['avg_score']}</b>/100."]

    if s["critical"]:
        parts.append(f"<b>{s['critical']}</b> alerta{'s fueron' if s['critical'] != 1 else ' fue'} "
                     f"de severidad crítica.")

    if data["by_type"]:
        top_type, top_count = next(iter(data["by_type"].items()))
        parts.append(f"El tipo más frecuente fue <b>{TYPE_LABELS.get(top_type, top_type)}</b> "
                     f"({top_count}).")

    if s["change_pct"] is not None:
        if s["change_pct"] > 0:
            parts.append(f"Esto representa un aumento del {s['change_pct']}% frente al periodo anterior.")
        elif s["change_pct"] < 0:
            parts.append(f"Esto representa una disminución del {abs(s['change_pct'])}% "
                         f"frente al periodo anterior.")
        else:
            parts.append("El volumen se mantuvo igual que en el periodo anterior.")

    parts.append(f"Se gestionó el {s['review_rate']}% de las alertas "
                 f"y {s['pending']} siguen sin revisar.")
    if s["false_pos"]:
        parts.append(f"{s['false_pos']} se marcaron como falso positivo "
                     f"(tasa del {s['fp_rate']}%), lo que alimenta el reentrenamiento del modelo.")
    return " ".join(parts)


def report_filename(data, extension):
    p    = data["period"]
    tipo = "semanal" if p["period"] == "weekly" else "mensual"
    return (f"sentryx_informe_{tipo}_{p['start_date'].isoformat()}"
            f"_a_{p['last_date'].isoformat()}.{extension}")


# ══════════════════════════════════════════════════════════
#  3a. Exportación CSV
# ══════════════════════════════════════════════════════════

def _csv_safe(value):
    """
    Neutralizar inyección de fórmulas en Excel (CSV injection).
    Los dominios y títulos vienen de correos externos: si un valor empieza con
    = + - @ Excel lo ejecutaría como fórmula. Se antepone una comilla simple.
    """
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def render_csv(data) -> bytes:
    """
    CSV listo para Excel en español:
      - separador ';' (Excel en es-CO usa la coma como separador decimal)
      - BOM UTF-8 para que las tildes se vean bien al abrirlo con doble clic
    """
    buf = io.StringIO()
    w   = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL)

    w.writerow(["fecha_deteccion", "titulo", "severidad", "tipo_phishing",
                "score_total", "score_encabezados", "score_contenido", "score_urls",
                "estado", "dominio_remitente", "tecnica_mitre", "campana",
                "cantidad_urls", "tiene_adjuntos"])

    for a in data["alerts"]:
        w.writerow([_csv_safe(v) for v in [
            timezone.localtime(a["detected_at"]).strftime("%Y-%m-%d %H:%M"),
            a["title"],
            SEVERITY_LABELS.get(a["severity"], a["severity"]),
            TYPE_LABELS.get(a["phishing_type"], a["phishing_type"]),
            round(a["risk_score"]),
            round(a["score_headers"]),
            round(a["score_content"]),
            round(a["score_urls"]),
            STATUS_LABELS.get(a["status"], a["status"]),
            a["sender_domain"] or "",
            a["mitre_technique"] or "",
            a["campaign__name"] or "",
            a["url_count"],
            "Sí" if a["has_attachments"] else "No",
        ]])

    return ("\ufeff" + buf.getvalue()).encode("utf-8")


# ══════════════════════════════════════════════════════════
#  3b. Exportación PDF
# ══════════════════════════════════════════════════════════

def render_pdf(data) -> bytes:
    # Importar ReportLab aquí para que el resto del sistema funcione aunque
    # la librería no esté instalada (solo fallaría la descarga en PDF).
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )
    from xml.sax.saxutils import escape

    NAVY   = colors.HexColor("#0f1e4a")
    BLUE   = colors.HexColor("#3b5bdb")
    GRAY   = colors.HexColor("#6b7280")
    LIGHT  = colors.HexColor("#f3f4f6")
    BORDER = colors.HexColor("#d1d5db")
    SEV_COLORS = {
        "CRITICAL": colors.HexColor("#dc2626"),
        "HIGH":     colors.HexColor("#ea580c"),
        "MEDIUM":   colors.HexColor("#ca8a04"),
        "LOW":      colors.HexColor("#16a34a"),
    }

    base   = getSampleStyleSheet()
    title  = ParagraphStyle("t",  parent=base["Title"], fontSize=18, textColor=NAVY,
                            spaceAfter=4, alignment=0)
    sub    = ParagraphStyle("s",  parent=base["Normal"], fontSize=10, textColor=GRAY)
    # keepWithNext evita que un título de sección quede solo al final de la página
    h2     = ParagraphStyle("h2", parent=base["Heading2"], fontSize=12.5, textColor=NAVY,
                            spaceBefore=14, spaceAfter=6, keepWithNext=1)
    body   = ParagraphStyle("b",  parent=base["Normal"], fontSize=9.5, leading=14)
    small  = ParagraphStyle("sm", parent=base["Normal"], fontSize=7.5, leading=9.5)
    note   = ParagraphStyle("n",  parent=base["Normal"], fontSize=8, leading=11, textColor=GRAY)
    kpi_v  = ParagraphStyle("kv", parent=base["Normal"], fontSize=17, leading=20,
                            alignment=TA_CENTER, textColor=NAVY, fontName="Helvetica-Bold")
    kpi_l  = ParagraphStyle("kl", parent=base["Normal"], fontSize=7.5, leading=9,
                            alignment=TA_CENTER, textColor=GRAY)

    def table_style(header_bg=NAVY):
        return TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), header_bg),
            ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, -1), 8.5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
            ("GRID",          (0, 0), (-1, -1), 0.4, BORDER),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ])

    s, p, u = data["summary"], data["period"], data["user"]
    tipo    = "semanal" if p["period"] == "weekly" else "mensual"
    gen     = data["generated_at"]
    story   = []

    # ── Encabezado ────────────────────────────────────────
    story.append(Paragraph(f"Informe {tipo} de detección de phishing", title))
    rango = f"{_fmt_date(p['start_date'])} - {_fmt_date(p['last_date'])}"
    estado = " (periodo en curso, datos parciales)" if p["in_progress"] else ""
    story.append(Paragraph(f"{escape(p['label'])} &nbsp;|&nbsp; {rango}{estado}", sub))
    story.append(Spacer(1, 8))

    meta = [
        ["Usuario", u["email"], "Rol", str(u["role"])],
        ["Organización", u["organization"] or "-",
         "Alcance", "Todos los usuarios" if u["is_admin"] else "Alertas propias"],
        ["Generado", f"{_fmt_date(gen.date())} {gen.strftime('%H:%M')}",
         "Zona horaria", "America/Bogota"],
    ]
    mt = Table(meta, colWidths=[2.6 * cm, 6.1 * cm, 2.4 * cm, 6.1 * cm])
    mt.setStyle(TableStyle([
        ("FONTSIZE",  (0, 0), (-1, -1), 8.5),
        ("TEXTCOLOR", (0, 0), (0, -1), GRAY),
        ("TEXTCOLOR", (2, 0), (2, -1), GRAY),
        ("FONTNAME",  (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTNAME",  (3, 0), (3, -1), "Helvetica-Bold"),
        ("LINEBELOW", (0, -1), (-1, -1), 0.6, BORDER),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(mt)

    # ── Resumen ejecutivo ─────────────────────────────────
    story.append(Paragraph("1. Resumen ejecutivo", h2))

    if s["change_pct"] is None:
        cambio = "sin datos previos"
    else:
        cambio = f"{'+' if s['change_pct'] > 0 else ''}{s['change_pct']}% vs anterior"

    kpis = [
        (s["total"],             "Alertas totales", cambio),
        (s["critical"],          "Críticas",        f"{s['high']} de severidad alta"),
        (f"{s['avg_score']}",    "Score promedio",  f"máximo {s['max_score']}"),
        (f"{s['review_rate']}%", "Gestionadas",     f"{s['pending']} pendientes"),
        (f"{s['fp_rate']}%",     "Falsos positivos", f"{s['false_pos']} marcados"),
    ]
    kpi_tbl = Table(
        [[Paragraph(str(v), kpi_v) for v, _, _ in kpis],
         [Paragraph(l, kpi_l) for _, l, _ in kpis],
         [Paragraph(f"<i>{escape(h)}</i>", kpi_l) for _, _, h in kpis]],
        colWidths=[3.44 * cm] * 5,
    )
    kpi_tbl.setStyle(TableStyle([
        ("BOX",        (0, 0), (-1, -1), 0.6, BORDER),
        ("INNERGRID",  (0, 0), (-1, -1), 0, colors.white),
        ("LINEAFTER",  (0, 0), (-2, -1), 0.4, BORDER),
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
    ]))
    story.append(kpi_tbl)
    story.append(Spacer(1, 8))
    story.append(Paragraph(build_executive_text(data), body))

    # ── Tendencia diaria ──────────────────────────────────
    story.append(Paragraph("2. Alertas por día", h2))
    daily  = data["daily"]
    values = [d["count"] for d in daily]
    drawing = Drawing(17 * cm, 5.2 * cm)
    chart   = VerticalBarChart()
    chart.x, chart.y = 1.1 * cm, 0.9 * cm
    chart.width, chart.height = 15.5 * cm, 3.9 * cm
    chart.data = [values]
    chart.bars[0].fillColor   = BLUE
    chart.bars[0].strokeColor = None
    chart.valueAxis.valueMin  = 0
    top = max(values) if values else 0
    chart.valueAxis.valueMax  = max(top + 1, 4)
    chart.valueAxis.valueStep = max(1, (chart.valueAxis.valueMax // 4) or 1)
    chart.valueAxis.labels.fontSize = 7
    chart.valueAxis.labels.fontName = "Helvetica"
    chart.categoryAxis.labels.fontName = "Helvetica"
    chart.categoryAxis.labels.fillColor = GRAY
    chart.valueAxis.labels.fillColor = GRAY
    chart.valueAxis.strokeColor = BORDER
    chart.categoryAxis.strokeColor = BORDER
    chart.categoryAxis.labels.fontSize = 6.5 if len(daily) > 10 else 7.5
    if p["period"] == "weekly":
        dias = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
        chart.categoryAxis.categoryNames = [f"{dias[d['date'].weekday()]} {d['date'].day}" for d in daily]
    else:
        # En el mensual se rotula un día de cada tres para que no se encimen
        chart.categoryAxis.categoryNames = [
            str(d["date"].day) if (i % 3 == 0 or i == len(daily) - 1) else ""
            for i, d in enumerate(daily)
        ]
    chart.barSpacing = 1
    drawing.add(chart)
    if top == 0:
        drawing.add(String(8.5 * cm, 2.8 * cm, "Sin alertas en el periodo",
                           fontSize=9, fillColor=GRAY, textAnchor="middle"))
    story.append(drawing)

    # ── Distribución por severidad, tipo y estado ────────
    story.append(Paragraph("3. Distribución de las alertas", h2))
    total = s["total"] or 1

    sev_rows = [["Severidad", "Cant.", "%"]]
    for k in SEVERITY_ORDER:
        sev_rows.append([SEVERITY_LABELS[k], data["by_severity"][k],
                         f"{round(data['by_severity'][k] / total * 100)}%"])
    sev_tbl = Table(sev_rows, colWidths=[2.6 * cm, 1.4 * cm, 1.4 * cm])
    st = table_style()
    for i, k in enumerate(SEVERITY_ORDER, start=1):
        st.add("TEXTCOLOR", (0, i), (0, i), SEV_COLORS[k])
        st.add("FONTNAME",  (0, i), (0, i), "Helvetica-Bold")
    sev_tbl.setStyle(st)

    type_rows = [["Tipo de phishing", "Cant."]]
    for k, v in data["by_type"].items():
        type_rows.append([TYPE_LABELS.get(k, k), v])
    if len(type_rows) == 1:
        type_rows.append(["Sin datos", 0])
    type_tbl = Table(type_rows, colWidths=[3.3 * cm, 1.3 * cm])
    type_tbl.setStyle(table_style())

    st_rows = [["Estado", "Cant."]]
    for k, label in STATUS_LABELS.items():
        st_rows.append([label, data["by_status"][k]])
    st_tbl = Table(st_rows, colWidths=[2.8 * cm, 1.3 * cm])
    st_tbl.setStyle(table_style())

    trio = Table([[sev_tbl, type_tbl, st_tbl]],
                 colWidths=[5.9 * cm, 5.1 * cm, 4.6 * cm])
    trio.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                              ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(trio)

    # ── Indicadores de amenaza ────────────────────────────
    story.append(Paragraph("4. Indicadores más frecuentes", h2))
    dom_rows = [["Dominio remitente", "Alertas"]] + \
               [[Paragraph(escape(r["sender_domain"]), small), r["c"]] for r in data["top_domains"]]
    if len(dom_rows) == 1:
        dom_rows.append(["Sin datos", "-"])
    dom_tbl = Table(dom_rows, colWidths=[4.2 * cm, 1.4 * cm])
    dom_tbl.setStyle(table_style())

    mitre_rows = [["Técnica MITRE ATT&CK", "Alertas"]] + \
                 [[r["mitre_technique"], r["c"]] for r in data["top_mitre"]]
    if len(mitre_rows) == 1:
        mitre_rows.append(["Sin datos", "-"])
    mitre_tbl = Table(mitre_rows, colWidths=[3.6 * cm, 1.4 * cm])
    mitre_tbl.setStyle(table_style())

    camp_rows = [["Campaña detectada", "Alertas"]] + \
                [[Paragraph(escape(r["campaign__name"]), small), r["c"]] for r in data["campaigns"]]
    if len(camp_rows) == 1:
        camp_rows.append(["Ninguna", "-"])
    camp_tbl = Table(camp_rows, colWidths=[4.6 * cm, 1.4 * cm])
    camp_tbl.setStyle(table_style())

    ind = Table([[dom_tbl, mitre_tbl, camp_tbl]],
                colWidths=[5.9 * cm, 5.3 * cm, 6.2 * cm])
    ind.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(ind)

    # ── Incidentes ────────────────────────────────────────
    story.append(Paragraph("5. Incidentes del periodo", h2))
    items = data["incidents"]["items"]
    if items:
        inc_rows = [["Creado", "Título", "Severidad", "Estado", "Cerrado"]]
        for it in items:
            inc_rows.append([
                _fmt_date(timezone.localtime(it["created_at"]).date()),
                Paragraph(escape(it["title"]), small),
                SEVERITY_LABELS.get(it["severity"], it["severity"]),
                INCIDENT_STATUS_LABELS.get(it["status"], it["status"]),
                _fmt_date(timezone.localtime(it["closed_at"]).date()) if it["closed_at"] else "-",
            ])
        inc_tbl = Table(inc_rows, colWidths=[2.3 * cm, 7.4 * cm, 2.2 * cm, 3 * cm, 2.3 * cm],
                        repeatRows=1)
        inc_tbl.setStyle(table_style())
        story.append(inc_tbl)
    else:
        story.append(Paragraph("No se crearon incidentes en este periodo.", body))

    # ── Detalle de alertas ────────────────────────────────
    alerts = data["alerts"]
    story.append(Paragraph("6. Detalle de alertas", h2))
    if alerts:
        rows = [["Fecha", "Alerta", "Sev.", "Tipo", "Score", "Estado", "Dominio"]]
        for a in alerts[:MAX_PDF_ROWS]:
            rows.append([
                timezone.localtime(a["detected_at"]).strftime("%d/%m %H:%M"),
                Paragraph(escape(a["title"]), small),
                SEVERITY_LABELS.get(a["severity"], a["severity"]),
                TYPE_LABELS.get(a["phishing_type"], a["phishing_type"]),
                round(a["risk_score"]),
                STATUS_LABELS.get(a["status"], a["status"]),
                Paragraph(escape(a["sender_domain"] or "-"), small),
            ])
        det = Table(rows, repeatRows=1,
                    colWidths=[2 * cm, 4.6 * cm, 1.5 * cm, 2.4 * cm, 1.2 * cm, 2.3 * cm, 3.2 * cm])
        st = table_style()
        st.add("FONTSIZE", (0, 1), (-1, -1), 7.5)
        st.add("ALIGN",    (4, 0), (4, -1), "CENTER")
        for i, a in enumerate(alerts[:MAX_PDF_ROWS], start=1):
            st.add("TEXTCOLOR", (2, i), (2, i), SEV_COLORS.get(a["severity"], GRAY))
            st.add("TEXTCOLOR", (4, i), (4, i), SEV_COLORS.get(a["severity"], GRAY))
            st.add("FONTNAME",  (4, i), (4, i), "Helvetica-Bold")
        det.setStyle(st)
        story.append(det)
        if len(alerts) > MAX_PDF_ROWS:
            story.append(Spacer(1, 4))
            story.append(Paragraph(
                f"Se muestran las {MAX_PDF_ROWS} alertas más recientes de {len(alerts)}. "
                f"Descarga el CSV para ver el listado completo.", note))
    else:
        story.append(Paragraph("No se registraron alertas en este periodo.", body))

    # ── Nota de privacidad ────────────────────────────────
    story.append(Spacer(1, 14))
    story.append(KeepTogether([
        Paragraph("Nota de privacidad", ParagraphStyle("np", parent=h2, fontSize=9.5, spaceBefore=0)),
        Paragraph(
            "Este informe no contiene datos personales. Los remitentes, destinatarios y asuntos "
            "de los correos se almacenan seudonimizados con SHA-256 y salt, conforme a la "
            "Ley 1581 de 2012 de Colombia. Solo se muestran los dominios remitentes y metadatos "
            "técnicos del análisis. La descarga de este documento quedó registrada en el log de "
            "auditoría del sistema.", note),
    ]))

    # ── Pie de página en cada hoja ────────────────────────
    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(1.8 * cm, 1.5 * cm, A4[0] - 1.8 * cm, 1.5 * cm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(GRAY)
        canvas.drawString(1.8 * cm, 1.05 * cm,
                          f"Sentryx v2 - Informe {tipo} - {p['label']} - {u['email']}")
        canvas.drawRightString(A4[0] - 1.8 * cm, 1.05 * cm, f"Página {doc.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm,
        topMargin=1.6 * cm, bottomMargin=2 * cm,
        title=f"Informe {tipo} Sentryx - {p['label']}",
        author="Sentryx v2", subject="Informe de detección de phishing",
    )
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()
