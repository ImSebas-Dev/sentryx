"""
Verificaciones funcionales tras ejecutar_prueba.py (correr con manage.py shell):
alertas y campañas creadas, seudonimización en BD, auditoría, informes PDF/CSV
con registro EXPORT, aislamiento por usuario y estadísticas del dashboard.

    docker compose exec -T backend python manage.py shell < docs/pruebas/verificar_funcional.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/tmp/pruebas")
from corpus_legitimos import LEGITIMOS  # noqa: E402
from corpus_phishing import PHISHING    # noqa: E402
from django.contrib.auth import get_user_model
from django.db.models import Count
from rest_framework.test import APIClient

from apps.alerts.models import Alert, PhishingCampaign
from apps.audit.models import AuditLog

User = get_user_model()
user = User.objects.get(email="prueba.sistema@sentryx.local")
other = User.objects.get(email="analista@sentryx.local")
admin = User.objects.get(email="admin@sentryx.local")
out = {}

alerts = Alert.objects.filter(owner=user)
out["alertas_creadas"] = alerts.count()
out["alertas_por_severidad"] = dict(alerts.values_list("severity").annotate(c=Count("id")))

camps = PhishingCampaign.objects.filter(owner=user)
out["campanas"] = [{"indicador": c.indicator, "alertas": c.alert_count} for c in camps]

# Seudonimización: ningún remitente, destinatario, asunto o frase del cuerpo en claro
corpus = LEGITIMOS + PHISHING
needles = set()
for e in corpus:
    addr = e["frm"].split("<")[-1].rstrip(">")
    needles.update({addr, e["to"], e["subject"], e["body"][:40]})
dump = json.dumps(list(alerts.values()), default=str, ensure_ascii=False)
out["texto_en_claro_encontrado"] = sorted(n for n in needles if n and n in dump)
out["hashes_completos"] = {
    f: alerts.exclude(**{f: ""}).filter(**{f"{f}__regex": r"^[0-9a-f]{64}$"}).count()
    for f in ("sender_hash", "recipient_hash", "subject_hash", "email_body_hash")
}
out["dominios_en_claro_ejemplo"] = list(alerts.values_list("sender_domain", flat=True)[:5])

# Auditoría
out["auditoria_analyze"] = AuditLog.objects.filter(user=user, action="ANALYZE").count()
out["auditoria_ip_hash_64"] = AuditLog.objects.filter(user=user, action="ANALYZE",
                                                      ip_hash__regex=r"^[0-9a-f]{64}$").count()

c = APIClient(SERVER_NAME="localhost")
c.force_authenticate(user)
stats = c.get("/api/v1/alerts/stats/").data
out["dashboard"] = {k: stats[k] for k in ("total", "new", "critical", "active_campaigns",
                                          "by_type", "by_severity")}
for exp in ("pdf", "csv"):
    r = c.get("/api/v1/alerts/report/", {"period": "weekly", "export": exp})
    out[f"informe_{exp}"] = {"status": r.status_code, "bytes": len(r.content),
                             "tipo": r["Content-Type"]}
out["auditoria_export"] = AuditLog.objects.filter(user=user, action="EXPORT").count()

# Aislamiento: otro analista no ve estas alertas; el admin sí
c2 = APIClient(SERVER_NAME="localhost")
c2.force_authenticate(other)
out["analista_ajeno_ve"] = c2.get("/api/v1/alerts/").data["count"]
c2.force_authenticate(admin)
out["admin_ve"] = c2.get("/api/v1/alerts/").data["count"]
a = alerts.first()
c2.force_authenticate(other)
out["analista_ajeno_detalle_status"] = c2.get(f"/api/v1/alerts/{a.pk}/").status_code

print("RESULTADO=" + json.dumps(out, ensure_ascii=False, default=str))
