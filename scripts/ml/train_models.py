"""
Sentryx v2 — Entrenamiento completo de los tres modelos ML.

Uso:
    cd ml_engine
    python ../scripts/ml/train_models.py [--feedback-csv ruta.csv] [--output-dir dir]

    --feedback-csv  CSV con correcciones de analistas (mismas columnas que el
                    dataset) que se añade al dataset base. Lo usa el
                    reentrenamiento activo (POST /admin/retrain del ML Engine).
    --output-dir    Directorio donde guardar los .joblib (por defecto
                    ml_engine/models/trained). El ML Engine entrena en un
                    directorio temporal y luego mueve los modelos de forma atómica.

    La variable de entorno SENTRYX_ML_ENGINE_DIR indica dónde está ml_engine
    cuando el script no se ejecuta desde el repositorio (p. ej. en el contenedor).

Salidas en ml_engine/models/trained/:
    headers_rf_v1.joblib     — Random Forest encabezados
    content_svm_v1.joblib    — TF-IDF + LinearSVC contenido (binario)
    type_classifier_v1.joblib— TF-IDF + LinearSVC tipo de phishing
    url_rf_v1.joblib         — Random Forest URLs

Salidas en ml_engine/models/reports/:
    training_report.json     — Métricas de todos los modelos
"""

import os
import sys
import json
import time
import re
import argparse
from pathlib import Path

# Añadir ml_engine al path
ML_ENGINE_DIR = Path(os.environ.get(
    "SENTRYX_ML_ENGINE_DIR",
    Path(__file__).resolve().parent.parent.parent / "ml_engine",
))
sys.path.insert(0, str(ML_ENGINE_DIR))

import numpy as np
import pandas as pd
import joblib

from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import LinearSVC
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.metrics import (classification_report, confusion_matrix,
                                f1_score, roc_auc_score, precision_score, recall_score)
from sklearn.calibration import CalibratedClassifierCV

from pipelines.email_headers import extract_header_features, FEATURE_ORDER as HEADER_FEATURES
from pipelines.email_content  import clean_html, extract_content_features
from pipelines.email_urls     import extract_url_features, FEATURE_ORDER as URL_FEATURES

URL_PATTERN   = re.compile(r"https?://[^\s\"'<>]+", re.I)
MODEL_DIR     = ML_ENGINE_DIR / "models" / "trained"
REPORT_DIR    = ML_ENGINE_DIR / "models" / "reports"
DATA_DIR      = ML_ENGINE_DIR / "data" / "processed"


GLOBAL_REPORT = {}


def load_dataset(feedback_csv: str | None = None) -> pd.DataFrame:
    """Carga el dataset procesado (real o sintético) y, si se indica, el feedback."""
    real_path  = DATA_DIR / "emails_dataset_real.csv"
    synth_path = DATA_DIR / "emails_dataset.csv"
    path = real_path if real_path.exists() else synth_path
    df   = pd.read_csv(path)
    print(f"Dataset: {path.name} — {len(df)} muestras")
    print(f"  Phishing: {df[df['label']==1].shape[0]}")
    print(f"  Legítimo: {df[df['label']==0].shape[0]}\n")

    if feedback_csv:
        fb = pd.read_csv(feedback_csv)
        # Solo columnas conocidas del dataset; las que falten quedan vacías
        fb = fb.reindex(columns=df.columns)
        df = pd.concat([df, fb], ignore_index=True)
        print(f"Feedback: {len(fb)} muestras añadidas desde {feedback_csv}")
        print(f"Total:    {len(df)} muestras\n")

    df["label"]         = df["label"].astype(int)
    df["phishing_type"] = df["phishing_type"].fillna("legitimate")
    return df


def save_model_report(model_key: str, metrics: dict, n_train: int, n_test: int,
                      extra: dict | None = None):
    """
    Guarda el reporte individual del modelo (models/reports/<model>.json).
    Es el formato que lee el ML Engine para comparar métricas antes y
    después del reentrenamiento.
    """
    report = {
        "model":           model_key,
        "f1_test":         metrics["f1"],
        "precision":       metrics["precision"],
        "recall":          metrics["recall"],
        "roc_auc":         metrics["roc_auc"],
        "f1_cv_mean":      metrics["cv_f1"],
        "n_train":         int(n_train),
        "n_test":          int(n_test),
        "false_positives": metrics["false_positives"],
        "false_negatives": metrics["false_negatives"],
        **(extra or {}),
    }
    with open(REPORT_DIR / f"{model_key}.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)


def print_metrics(name, y_test, y_pred, y_proba, cv_f1):
    f1      = f1_score(y_test, y_pred)
    prec    = precision_score(y_test, y_pred)
    rec     = recall_score(y_test, y_pred)
    auc     = roc_auc_score(y_test, y_proba)
    cm      = confusion_matrix(y_test, y_pred)

    print(f"  F1:          {f1:.4f}")
    print(f"  Precision:   {prec:.4f}  (↑ reduce falsos positivos)")
    print(f"  Recall:      {rec:.4f}  (↑ reduce falsos negativos)")
    print(f"  ROC-AUC:     {auc:.4f}")
    print(f"  CV-F1 (5k):  {cv_f1:.4f}")
    print(f"  FP: {cm[0,1]}  FN: {cm[1,0]}")
    print(classification_report(y_test, y_pred, target_names=["Legítimo","Phishing"]))

    return {"f1": round(float(f1),4), "precision": round(float(prec),4),
            "recall": round(float(rec),4), "roc_auc": round(float(auc),4),
            "cv_f1": round(float(cv_f1),4),
            "false_positives": int(cm[0,1]), "false_negatives": int(cm[1,0])}


# ═══════════════════════════════════════════════════════════
# MODELO 1: Encabezados — Random Forest
# ═══════════════════════════════════════════════════════════
def train_headers(df: pd.DataFrame):
    print("=" * 60)
    print("MODELO 1 — Encabezados (Random Forest)")
    print("=" * 60)
    t0 = time.time()

    X_rows = []
    for _, row in df.iterrows():
        h = {
            "from":                   str(row.get("from", row.get("sender_hash", ""))),
            "reply-to":               str(row.get("reply_to", "")),
            "authentication-results": str(row.get("auth_results", "")),
            "received":               ["hop"] * int(row.get("received_hops", 3)),
            "subject":                str(row.get("subject", "")),
        }
        feats = extract_header_features(h)
        X_rows.append([feats[f] for f in HEADER_FEATURES])

    X, y = np.array(X_rows), df["label"].values
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=.2, random_state=42, stratify=y)

    rf = RandomForestClassifier(n_estimators=200, max_depth=12, min_samples_split=5,
                                    min_samples_leaf=2, class_weight="balanced",
                                    random_state=42, n_jobs=-1)
    rf.fit(X_tr, y_tr)

    y_pred  = rf.predict(X_te)
    y_proba = rf.predict_proba(X_te)[:, 1]
    cv_f1   = cross_val_score(rf, X, y, cv=StratifiedKFold(5), scoring="f1").mean()

    metrics = print_metrics("Headers", y_te, y_pred, y_proba, cv_f1)

    # Feature importance
    imp = sorted(zip(HEADER_FEATURES, rf.feature_importances_), key=lambda x: x[1], reverse=True)
    print("  Top features:")
    for feat, val in imp[:8]:
        print(f"    {feat:<30} {val:.4f}")

    path = MODEL_DIR / "headers_rf_v1.joblib"
    joblib.dump(rf, path)
    print(f"\n  ✓ Guardado: {path} ({path.stat().st_size//1024} KB) en {time.time()-t0:.1f}s\n")

    GLOBAL_REPORT["headers_rf_v1"] = {**metrics, "top_features": [f for f,_ in imp[:5]]}
    save_model_report("headers_rf_v1", metrics, len(y_tr), len(y_te),
                      {"n_features": len(HEADER_FEATURES)})


# ═══════════════════════════════════════════════════════════
# MODELO 2: Contenido — TF-IDF + LinearSVC
# ═══════════════════════════════════════════════════════════
def train_content(df: pd.DataFrame):
    print("=" * 60)
    print("MODELO 2 — Contenido (TF-IDF + LinearSVC)")
    print("=" * 60)
    t0 = time.time()

    df["text"] = (df["subject"].fillna("").astype(str) + " " +
                    df["body"].fillna("").astype(str).apply(clean_html)).str.lower()
    y_binary = df["label"].values
    y_type   = df["phishing_type"].values

    X_tr, X_te, y_tr, y_te, yt_tr, yt_te = train_test_split(
        df["text"].values, y_binary, y_type,
        test_size=.2, random_state=42, stratify=y_binary)

    # Pipeline binario
    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(max_features=10000, ngram_range=(1,2),
                                    sublinear_tf=True, min_df=2, strip_accents="unicode")),
        ("clf",   CalibratedClassifierCV(
            LinearSVC(C=1.0, max_iter=3000, class_weight="balanced", random_state=42),
            cv=3, method="sigmoid")),
    ])
    pipeline.fit(X_tr, y_tr)
    y_pred  = pipeline.predict(X_te)
    y_proba = pipeline.predict_proba(X_te)[:, 1]
    cv_f1   = cross_val_score(pipeline, df["text"].values, y_binary,
                                cv=StratifiedKFold(5), scoring="f1").mean()
    metrics = print_metrics("Content", y_te, y_pred, y_proba, cv_f1)

    # Top words
    feature_names = pipeline.named_steps["tfidf"].get_feature_names_out()
    calib         = pipeline.named_steps["clf"]
    coefs         = np.array([cc.estimator.coef_[0]
                                for cc in calib.calibrated_classifiers_]).mean(axis=0)
    top_phishing  = [feature_names[i] for i in coefs.argsort()[-10:]][::-1]
    print(f"  Top palabras phishing: {top_phishing[:8]}")

    path = MODEL_DIR / "content_svm_v1.joblib"
    joblib.dump(pipeline, path)
    print(f"\n  ✓ Binario guardado: {path} ({path.stat().st_size//1024} KB)")

    # Clasificador de tipo
    X_ph_tr = X_tr[yt_tr != "legitimate"]
    y_ph_tr = yt_tr[yt_tr != "legitimate"]
    X_ph_te = X_te[yt_te != "legitimate"]
    y_ph_te = yt_te[yt_te != "legitimate"]

    if len(np.unique(y_ph_tr)) > 1:
        type_pipe = Pipeline([
            ("tfidf", TfidfVectorizer(max_features=6000, ngram_range=(1,2),
                                        sublinear_tf=True, min_df=1, strip_accents="unicode")),
            ("clf",   CalibratedClassifierCV(
                LinearSVC(C=0.5, max_iter=3000, class_weight="balanced", random_state=42),
                cv=3, method="sigmoid")),
        ])
        type_pipe.fit(X_ph_tr, y_ph_tr)
        yt_pred = type_pipe.predict(X_ph_te)
        f1_type = f1_score(y_ph_te, yt_pred, average="weighted") if len(X_ph_te) > 0 else 0
        print(f"  Tipo F1-weighted: {f1_type:.4f}")
        print(classification_report(y_ph_te, yt_pred))

        type_path = MODEL_DIR / "type_classifier_v1.joblib"
        joblib.dump(type_pipe, type_path)
        print(f"  ✓ Tipo guardado: {type_path} ({type_path.stat().st_size//1024} KB)")
        metrics["f1_type_weighted"] = round(float(f1_type), 4)

    print(f"\n  Completado en {time.time()-t0:.1f}s\n")
    GLOBAL_REPORT["content_svm_v1"] = {**metrics, "top_phishing_words": top_phishing[:8]}
    save_model_report("content_svm_v1", metrics, len(y_tr), len(y_te), {
        "f1_type_weighted":   metrics.get("f1_type_weighted"),
        "vocab_size":         len(feature_names),
        "top_phishing_words": top_phishing[:8],
    })


# ═══════════════════════════════════════════════════════════
# MODELO 3: URLs — Random Forest
# ═══════════════════════════════════════════════════════════
def train_urls(df: pd.DataFrame):
    print("=" * 60)
    print("MODELO 3 — URLs embebidas (Random Forest)")
    print("=" * 60)
    t0 = time.time()

    url_rows = []
    for _, row in df.iterrows():
        body  = str(row.get("body", ""))
        label = int(row["label"])
        urls  = URL_PATTERN.findall(body)[:3]
        if urls:
            for url in urls:
                url_rows.append({"url": url, "label": label})
        elif label == 0:
            url_rows.append({"url": "https://amazon.com/orders", "label": 0})

    url_df = pd.DataFrame(url_rows)
    print(f"  Dataset URLs: {len(url_df)} ({url_df['label'].sum()} phishing)\n")

    X_rows = [[extract_url_features(u)[f] for f in URL_FEATURES]
                for u in url_df["url"]]
    X, y = np.array(X_rows), url_df["label"].values
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=.2, random_state=42, stratify=y)

    rf = RandomForestClassifier(n_estimators=150, max_depth=10, min_samples_split=4,
                                    min_samples_leaf=2, class_weight="balanced",
                                    random_state=42, n_jobs=-1)
    rf.fit(X_tr, y_tr)
    y_pred  = rf.predict(X_te)
    y_proba = rf.predict_proba(X_te)[:, 1]
    cv_f1   = cross_val_score(rf, X, y, cv=StratifiedKFold(5), scoring="f1").mean()
    metrics = print_metrics("URLs", y_te, y_pred, y_proba, cv_f1)

    imp = sorted(zip(URL_FEATURES, rf.feature_importances_), key=lambda x: x[1], reverse=True)
    print("  Top features:")
    for feat, val in imp[:6]:
        print(f"    {feat:<30} {val:.4f}")

    path = MODEL_DIR / "url_rf_v1.joblib"
    joblib.dump(rf, path)
    print(f"\n  ✓ Guardado: {path} ({path.stat().st_size//1024} KB) en {time.time()-t0:.1f}s\n")
    GLOBAL_REPORT["url_rf_v1"] = {**metrics, "top_features": [f for f,_ in imp[:5]]}
    save_model_report("url_rf_v1", metrics, len(y_tr), len(y_te),
                      {"n_features": len(URL_FEATURES)})


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Entrena los tres modelos de Sentryx.")
    parser.add_argument("--feedback-csv", help="CSV de feedback de analistas a añadir al dataset")
    parser.add_argument("--output-dir",   help="Directorio de salida de los .joblib")
    args = parser.parse_args()

    if args.output_dir:
        MODEL_DIR = Path(args.output_dir)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    print("\n" + "═"*60)
    print("Sentryx v2 — Entrenamiento de modelos ML")
    print("═"*60 + "\n")

    df = load_dataset(args.feedback_csv)
    train_headers(df)
    train_content(df)
    train_urls(df)

    # Reporte consolidado
    report_path = REPORT_DIR / "training_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(GLOBAL_REPORT, f, indent=2, ensure_ascii=False)

    print("=" * 60)
    print("RESUMEN FINAL")
    print("=" * 60)
    for model, m in GLOBAL_REPORT.items():
        print(f"\n{model}:")
        print(f"  F1={m['f1']:.4f}  Prec={m['precision']:.4f}  Rec={m['recall']:.4f}  AUC={m['roc_auc']:.4f}")
        print(f"  FP={m['false_positives']}  FN={m['false_negatives']}")

    print(f"\n✓ Reporte guardado: {report_path}")
    print("\nModelos listos. Para usar en el ML Engine, reinicia el contenedor:")
    print("  docker compose restart ml_engine")
