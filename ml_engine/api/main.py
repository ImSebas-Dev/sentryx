"""
Sentryx v2 — ML Engine API
FastAPI app que expone el ensemble de detección de phishing por correo.
"""
import os
import sys
import csv
import json
import time
import shutil
import logging
import tempfile
import threading
import subprocess
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from decouple import config
from typing import Optional, Dict, Any, List

from pipelines.ensemble import EmailEnsemble

logger = logging.getLogger("uvicorn.error")

# ── Configuración ─────────────────────────────────────────
ML_ENGINE_API_KEY = config("ML_ENGINE_API_KEY", default="dev-key")
api_key_header    = APIKeyHeader(name="X-API-Key", auto_error=False)

ML_ENGINE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR     = ML_ENGINE_DIR / "models" / "trained"
REPORT_DIR    = ML_ENGINE_DIR / "models" / "reports"
MODEL_REPORTS = ["headers_rf_v1.json", "content_svm_v1.json", "url_rf_v1.json"]

# Script de entrenamiento: montado en el contenedor (docker-compose) o,
# fuera de Docker, en la ruta del repositorio.
TRAIN_SCRIPT = Path(config(
    "ML_TRAIN_SCRIPT",
    default=str(ML_ENGINE_DIR.parent / "scripts" / "ml" / "train_models.py"),
))
TRAIN_TIMEOUT = config("ML_TRAIN_TIMEOUT_SECONDS", default=540, cast=int)

app = FastAPI(
    title="Sentryx ML Engine — Email Phishing Detection",
    description=(
        "Motor de Machine Learning para detección de phishing por correo electrónico. "
        "Analiza encabezados, contenido y URLs mediante un ensemble de tres modelos Scikit-learn."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://backend:8000"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# ── Ensemble con recarga en caliente ──────────────────────
# Se carga al iniciar y se vuelve a cargar cuando cambian los .joblib
# (tras un reentrenamiento). Comparar la fecha de modificación en cada
# petición hace que todos los workers de uvicorn recarguen, no solo el
# que atendió el reentrenamiento.
_ensemble_lock = threading.Lock()


def _models_mtime() -> float:
    mtime = 0.0
    for path in MODEL_DIR.glob("*.joblib"):
        try:
            mtime = max(mtime, path.stat().st_mtime)
        except OSError:
            pass
    return mtime


_ensemble       = EmailEnsemble()
_ensemble_mtime = _models_mtime()


def get_ensemble(force: bool = False) -> EmailEnsemble:
    global _ensemble, _ensemble_mtime
    mtime = _models_mtime()
    if force or mtime > _ensemble_mtime:
        with _ensemble_lock:
            if force or mtime > _ensemble_mtime:
                _ensemble       = EmailEnsemble()
                _ensemble_mtime = mtime
                logger.info(f"[ML] Modelos recargados: {_ensemble.models_status}")
    return _ensemble


# ── Auth ──────────────────────────────────────────────────
async def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != ML_ENGINE_API_KEY:
        raise HTTPException(status_code=403, detail="API key inválida")
    return api_key


# ── Schemas ───────────────────────────────────────────────
class EmailHeaders(BaseModel):
    """Encabezados del correo a analizar."""
    from_addr:              Optional[str] = Field(None, alias="from")
    subject:                Optional[str] = None
    reply_to:               Optional[str] = Field(None, alias="reply-to")
    authentication_results: Optional[str] = Field(None, alias="authentication-results")
    received:               Optional[List[str]] = None
    x_mailer:               Optional[str] = Field(None, alias="x-mailer")
    x_spam_status:          Optional[str] = Field(None, alias="x-spam-status")
    date:                   Optional[str] = None

    class Config:
        populate_by_name = True


class EmailAnalysisRequest(BaseModel):
    """Correo completo para análisis de phishing."""
    headers:   Optional[EmailHeaders] = None
    body_text: str = Field(default="", description="Cuerpo en texto plano")
    body_html: Optional[str] = Field(None, description="Cuerpo en HTML (preferido si está disponible)")

    class Config:
        json_schema_extra = {
            "example": {
                "headers": {
                    "from": "soporte@bancolombia-seguro.tk",
                    "subject": "URGENTE: Verifica tu cuenta ahora",
                    "authentication-results": "spf=fail dkim=none dmarc=fail",
                },
                "body_text": "Estimado cliente, tu cuenta será suspendida. Haz clic aquí para verificar: http://192.168.1.1/login",
                "body_html": None,
            }
        }


class LayerScores(BaseModel):
    headers: float
    content: float
    urls:    float


class URLResult(BaseModel):
    url_truncated: str
    score:         float


class EmailAnalysisResponse(BaseModel):
    risk_score:        float = Field(description="Score final del ensemble (0–100)")
    classification:    str   = Field(description="legitimate | suspicious | phishing | critical")
    phishing_type:     str   = Field(description="Tipo de phishing detectado")
    mitre_technique:   str   = Field(description="Sub-técnica MITRE ATT&CK")
    mitre_tactic:      str
    scores_by_layer:   LayerScores
    url_count:         int
    urls_analyzed:     List[URLResult]
    model_versions:    Dict[str, str]
    inference_ms:      float


# ── Endpoints ─────────────────────────────────────────────
@app.get("/health", tags=["sistema"])
def health():
    return {
        "status":  "ok",
        "service": "sentryx-ml-engine",
        "version": "2.0.0",
        "models":  get_ensemble().models_status,
    }


@app.post(
    "/analyze/email",
    response_model=EmailAnalysisResponse,
    tags=["phishing"],
    summary="Analizar correo completo en busca de phishing",
)
async def analyze_email(
    body: EmailAnalysisRequest,
    _: str = Depends(verify_api_key),
):
    """
    Endpoint principal. Recibe un correo (encabezados + cuerpo) y retorna
    el análisis completo del ensemble de tres modelos.
    """
    t0 = time.perf_counter()

    # Convertir el schema Pydantic a dict plano para el ensemble
    headers_dict = {}
    if body.headers:
        h = body.headers
        if h.from_addr:              headers_dict["from"]                   = h.from_addr
        if h.subject:                headers_dict["subject"]                = h.subject
        if h.reply_to:               headers_dict["reply-to"]               = h.reply_to
        if h.authentication_results: headers_dict["authentication-results"] = h.authentication_results
        if h.received:               headers_dict["received"]               = h.received
        if h.x_mailer:               headers_dict["x-mailer"]               = h.x_mailer
        if h.x_spam_status:          headers_dict["x-spam-status"]          = h.x_spam_status

    email_dict = {
        "headers":   headers_dict,
        "body_text": body.body_text,
        "body_html": body.body_html or body.body_text,
    }

    result = get_ensemble().predict(email_dict)
    ms     = round((time.perf_counter() - t0) * 1000, 2)

    return EmailAnalysisResponse(
        risk_score=result["risk_score"],
        classification=result["classification"],
        phishing_type=result["phishing_type"],
        mitre_technique=result["mitre_technique"],
        mitre_tactic=result["mitre_tactic"],
        scores_by_layer=LayerScores(**result["scores_by_layer"]),
        url_count=result["url_count"],
        urls_analyzed=[URLResult(**u) for u in result.get("urls_analyzed", [])],
        model_versions=result["model_versions"],
        inference_ms=ms,
    )


@app.post(
    "/analyze/url",
    tags=["phishing"],
    summary="Analizar una URL individual (uso desde el dashboard)",
)
async def analyze_url(
    data: dict,
    _: str = Depends(verify_api_key),
):
    """Analiza una sola URL — útil para el analizador manual del dashboard."""
    from pipelines.email_urls import extract_url_features, URLsPipeline
    url = data.get("url", "")
    if not url:
        raise HTTPException(status_code=422, detail="El campo 'url' es requerido")

    pipe    = URLsPipeline()
    result  = pipe.predict(url)
    return result


# ── Reentrenamiento activo ────────────────────────────────
FEEDBACK_COLUMNS = [
    "label", "phishing_type", "from", "subject",
    "body", "auth_results", "reply_to", "received_hops",
]

_retrain_lock = threading.Lock()


class RetrainRequest(BaseModel):
    """Muestras de feedback de analistas (mismas columnas que el dataset)."""
    feedback: List[Dict[str, Any]] = Field(default_factory=list)


def read_current_metrics() -> dict:
    """Consolida las métricas de los reportes individuales de cada modelo."""
    metrics = {}
    for report_file in MODEL_REPORTS:
        path = REPORT_DIR / report_file
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"[Retrain] No se pudo leer {report_file}: {exc}")
            continue
        metrics[report_file.replace(".json", "")] = {
            "f1":      data.get("f1_test") or data.get("f1_binary_test", 0),
            "roc_auc": data.get("roc_auc", 0),
            "n_train": data.get("n_train", 0),
            "n_test":  data.get("n_test", 0),
        }

    f1_values = [m["f1"] for m in metrics.values() if m.get("f1")]
    metrics["f1"] = round(sum(f1_values) / len(f1_values), 4) if f1_values else 0
    return metrics


def _write_feedback_csv(rows: List[Dict[str, Any]]) -> Optional[str]:
    if not rows:
        return None
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline="", encoding="utf-8",
    )
    with tmp:
        writer = csv.DictWriter(tmp, fieldnames=FEEDBACK_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in FEEDBACK_COLUMNS})
    return tmp.name


@app.post("/admin/retrain", tags=["sistema"], summary="Reentrenar los modelos con feedback")
def retrain(body: RetrainRequest, _: str = Depends(verify_api_key)):
    """
    Reentrena los tres modelos (dataset base + feedback) con train_models.py.
    Los modelos se generan en un directorio temporal y solo se reemplazan
    si el entrenamiento termina bien; si falla, los reportes se restauran.
    Es síncrono: tarda unos minutos (FastAPI lo ejecuta en un hilo aparte).
    """
    if not TRAIN_SCRIPT.exists():
        raise HTTPException(
            status_code=500,
            detail=f"No se encontró el script de entrenamiento en {TRAIN_SCRIPT}",
        )
    if not _retrain_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Ya hay un reentrenamiento en curso.")

    feedback_csv = None
    staging_dir  = None
    report_backup: Dict[Path, bytes] = {}
    try:
        metrics_before = read_current_metrics()

        for name in MODEL_REPORTS + ["training_report.json"]:
            path = REPORT_DIR / name
            if path.exists():
                report_backup[path] = path.read_bytes()

        feedback_csv = _write_feedback_csv(body.feedback)
        # Mismo volumen que los modelos → os.replace es atómico
        staging_dir  = Path(tempfile.mkdtemp(prefix=".staging-", dir=MODEL_DIR))

        cmd = [sys.executable, str(TRAIN_SCRIPT), "--output-dir", str(staging_dir)]
        if feedback_csv:
            cmd += ["--feedback-csv", feedback_csv]

        env = os.environ.copy()
        env["SENTRYX_ML_ENGINE_DIR"] = str(ML_ENGINE_DIR)
        env["PYTHONPATH"]            = str(ML_ENGINE_DIR)
        env["PYTHONIOENCODING"]      = "utf-8"

        logger.info(f"[Retrain] Iniciando con {len(body.feedback)} muestras de feedback")
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8",
                timeout=TRAIN_TIMEOUT, env=env, cwd=str(ML_ENGINE_DIR),
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"El entrenamiento superó el límite de {TRAIN_TIMEOUT} s.")

        if proc.returncode != 0:
            raise RuntimeError(f"train_models.py falló:\n{proc.stderr[-2000:]}")

        new_models = list(staging_dir.glob("*.joblib"))
        if not new_models:
            raise RuntimeError("El entrenamiento no generó ningún modelo.")
        for model in new_models:
            os.replace(model, MODEL_DIR / model.name)

        get_ensemble(force=True)
        metrics_after = read_current_metrics()
        # El modelo de encabezados usa todas las muestras (base + feedback)
        headers_m = metrics_after.get("headers_rf_v1", {})
        total     = headers_m.get("n_train", 0) + headers_m.get("n_test", 0)
        logger.info(f"[Retrain] Completado. F1 {metrics_before.get('f1')} → {metrics_after.get('f1')}")

        return {
            "status":         "completed",
            "samples_used":   len(body.feedback),
            "total_samples":  total,
            "metrics_before": metrics_before,
            "metrics_after":  metrics_after,
            "log_tail":       proc.stdout[-1500:],
        }

    except RuntimeError as exc:
        for path, content in report_backup.items():
            path.write_bytes(content)
        logger.error(f"[Retrain] {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

    finally:
        if feedback_csv and os.path.exists(feedback_csv):
            os.unlink(feedback_csv)
        if staging_dir:
            shutil.rmtree(staging_dir, ignore_errors=True)
        _retrain_lock.release()


@app.post("/admin/reload", tags=["sistema"], summary="Recargar los modelos desde disco")
def reload_models(_: str = Depends(verify_api_key)):
    return {"status": "ok", "models": get_ensemble(force=True).models_status}
