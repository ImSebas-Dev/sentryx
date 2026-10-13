"""
Prueba del sistema Sentryx v2 con 100 correos (docs/pruebas).

Envía cada correo a POST /api/v1/alerts/analyze/ a través de nginx, como lo
haría el dashboard o la extensión, con un usuario analista dedicado a la
prueba (prueba.sistema@sentryx.local). Guarda cada respuesta en
resultados.json y calcula las métricas en metricas.json.

Uso (dentro de la red de Docker, desde el contenedor backend):
    docker cp docs/pruebas sentryx_backend:/tmp/pruebas
    docker compose exec backend python /tmp/pruebas/ejecutar_prueba.py
"""
import json
import statistics
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from corpus_legitimos import LEGITIMOS  # noqa: E402
from corpus_phishing import PHISHING    # noqa: E402

API = "http://nginx/api/v1"
HOST = {"Host": "localhost"}          # ALLOWED_HOSTS del backend
USER = {"email": "prueba.sistema@sentryx.local", "password": "PruebaSistema2026"}


def received(hops):
    return [f"from mx{i}.relay.example by mx{i + 1}.relay.example with ESMTPS" for i in range(hops)]


def payload(e):
    return {
        "headers": {
            "from_addr": e["frm"], "to_addr": e["to"], "subject": e["subject"],
            "reply_to": e["reply_to"], "authentication_results": e["auth"],
            "received": received(e["hops"]),
        },
        "body_text": e["body"],
    }


def main():
    corpus = LEGITIMOS + PHISHING
    assert len(corpus) == 100 and len({e["id"] for e in corpus}) == 100

    c = httpx.Client(timeout=30, headers=HOST)
    tok = c.post(f"{API}/auth/token/", json=USER)
    tok.raise_for_status()
    auth = {"Authorization": f"Bearer {tok.json()['access']}"}

    results = []
    for e in corpus:
        t0 = time.perf_counter()
        r = c.post(f"{API}/alerts/analyze/", json=payload(e), headers=auth)
        rtt = (time.perf_counter() - t0) * 1000
        r.raise_for_status()
        d = r.json()
        results.append({
            "id": e["id"], "expected_label": e["label"], "expected_type": e["type"],
            "subject": e["subject"], "from": e["frm"], "basis": e["basis"],
            "risk_score": d["risk_score"], "classification": d["classification"],
            "predicted_type": d["phishing_type"], "mitre": d["mitre_technique"],
            "scores": d["scores_by_layer"], "alert_id": d["alert_id"],
            "alert_created": d["alert_created"], "inference_ms": d["inference_ms"],
            "roundtrip_ms": round(rtt, 1), "http_status": r.status_code,
        })
        print(f"{e['id']} {e['type']:10} -> {d['classification']:10} {d['risk_score']:5.1f} "
              f"{d['phishing_type']:10} {d['mitre_technique']}")

    (HERE / "resultados.json").write_text(json.dumps(results, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    (HERE / "metricas.json").write_text(json.dumps(metrics(results), ensure_ascii=False, indent=1),
                                        encoding="utf-8")


def metrics(res, threshold_label="suspicious"):
    """Positivo = el sistema creó alerta (clasificación ≥ sospechoso, score ≥ 40)."""
    tp = sum(r["expected_label"] == "phishing" and r["alert_created"] for r in res)
    fn = sum(r["expected_label"] == "phishing" and not r["alert_created"] for r in res)
    fp = sum(r["expected_label"] == "legitimate" and r["alert_created"] for r in res)
    tn = sum(r["expected_label"] == "legitimate" and not r["alert_created"] for r in res)
    prec = tp / (tp + fp) if tp + fp else 0
    rec = tp / (tp + fn) if tp + fn else 0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0

    by_type = {}
    for t in sorted({r["expected_type"] for r in res}):
        rows = [r for r in res if r["expected_type"] == t]
        by_type[t] = {
            "n": len(rows),
            "detected": sum(r["alert_created"] for r in rows),
            "type_correct": sum(r["predicted_type"] == t for r in rows),
            "mean_score": round(statistics.mean(r["risk_score"] for r in rows), 1),
            "classifications": {c: sum(r["classification"] == c for r in rows)
                                for c in ("legitimate", "suspicious", "phishing", "critical")},
        }
    lat = [r["inference_ms"] for r in res]
    rtt = [r["roundtrip_ms"] for r in res]
    return {
        "confusion": {"tp": tp, "fn": fn, "fp": fp, "tn": tn},
        "accuracy": round((tp + tn) / len(res), 4), "precision": round(prec, 4),
        "recall": round(rec, 4), "f1": round(f1, 4),
        "false_positive_rate": round(fp / (fp + tn), 4) if fp + tn else 0,
        "by_type": by_type,
        "latency_ms": {"inference_mean": round(statistics.mean(lat), 1),
                       "inference_p95": round(sorted(lat)[int(0.95 * len(lat)) - 1], 1),
                       "roundtrip_mean": round(statistics.mean(rtt), 1),
                       "roundtrip_p95": round(sorted(rtt)[int(0.95 * len(rtt)) - 1], 1)},
    }


if __name__ == "__main__":
    main()
