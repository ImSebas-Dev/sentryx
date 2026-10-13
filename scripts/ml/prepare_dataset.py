"""
Sentryx v2 — Preparación de datasets reales de phishing por correo.

Datasets a usar (todos públicos y gratuitos):
1. SpamAssassin Public Corpus
    URL: https://spamassassin.apache.org/old/publiccorpus/
    ~6000 correos etiquetados spam/ham

2. Nazario Phishing Email Dataset
    URL: https://www.kaggle.com/datasets/subhajournal/phishingemails
    ~18,000 correos de phishing

3. CEAS 2008 Spam Challenge Dataset
    URL: http://www.ceas.cc/2008/index.html

4. Enron Email Dataset (correos legítimos)
    URL: https://www.kaggle.com/datasets/wcukierski/enron-email-dataset

INSTRUCCIONES:
1. Descargar los datasets manualmente (requieren registro en Kaggle)
2. Guardar en ml_engine/data/raw/
3. Ejecutar este script: python scripts/ml/prepare_dataset.py

Estructura esperada en data/raw/:
    - nazario_phishing.csv     (columnas: Email Text, Email Type)
    - enron_emails.csv         (columnas: file, message)
    - spamassassin_spam/       (archivos .txt de spam)
    - spamassassin_ham/        (archivos .txt de ham/legítimos)
"""

import os
import re
import hashlib
import email
import pandas as pd
from pathlib import Path
from typing import Optional

RAW_DIR       = Path(__file__).parent.parent.parent / "ml_engine" / "data" / "raw"
PROCESSED_DIR = Path(__file__).parent.parent.parent / "ml_engine" / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def parse_email_file(path: Path) -> Optional[dict]:
    """Parsea un archivo .eml o .txt de correo."""
    try:
        with open(path, "rb") as f:
            msg = email.message_from_bytes(f.read())

        subject = str(msg.get("subject", ""))
        from_   = str(msg.get("from", ""))
        auth    = str(msg.get("authentication-results", ""))

        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    try:
                        body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                        break
                    except Exception:
                        pass
        else:
            try:
                body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
            except Exception:
                body = str(msg.get_payload())

        return {"from": from_, "subject": subject, "body": body[:2000],
                "auth_results": auth}
    except Exception:
        return None


def load_nazario(path: Path) -> pd.DataFrame:
    """Carga el dataset de Nazario desde CSV de Kaggle."""
    if not path.exists():
        print(f"  ⚠ No encontrado: {path}")
        return pd.DataFrame()

    df = pd.read_csv(path)
    # El dataset tiene columnas "Email Text" y "Email Type"
    if "Email Text" not in df.columns:
        # Intentar variaciones de nombre
        df.columns = df.columns.str.strip().str.lower()
        text_col = next((c for c in df.columns if "text" in c or "body" in c), None)
        type_col = next((c for c in df.columns if "type" in c or "label" in c), None)
        if not text_col or not type_col:
            print(f"  ⚠ Columnas no reconocidas en {path}: {list(df.columns)}")
            return pd.DataFrame()
        df = df.rename(columns={text_col: "Email Text", type_col: "Email Type"})

    df["label"]        = df["Email Type"].str.lower().str.contains("phish").astype(int)
    df["body"]         = df["Email Text"].fillna("").astype(str).str[:2000]
    df["subject"]      = ""
    df["from"]         = ""
    df["auth_results"] = ""
    df["phishing_type"]= df["label"].apply(lambda x: "generic" if x == 1 else "legitimate")

    print(f"  ✓ Nazario: {len(df)} correos ({df['label'].sum()} phishing)")
    return df[["label", "phishing_type", "from", "subject", "body", "auth_results"]]


def load_spamassassin(spam_dir: Path, ham_dir: Path) -> pd.DataFrame:
    """Carga correos de SpamAssassin desde directorios."""
    rows = []

    for label, directory, ptype in [(1, spam_dir, "generic"), (0, ham_dir, "legitimate")]:
        if not directory.exists():
            print(f"  ⚠ No encontrado: {directory}")
            continue
        files = list(directory.glob("*.txt")) + list(directory.glob("*"))
        files = [f for f in files if f.is_file()][:2000]

        for fpath in files:
            parsed = parse_email_file(fpath)
            if parsed:
                rows.append({**parsed, "label": label, "phishing_type": ptype})

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    print(f"  ✓ SpamAssassin: {len(df)} correos ({df['label'].sum()} spam)")
    return df


def load_enron(path: Path, max_samples: int = 2000) -> pd.DataFrame:
    """Carga correos legítimos del dataset Enron."""
    if not path.exists():
        print(f"  ⚠ No encontrado: {path}")
        return pd.DataFrame()

    df = pd.read_csv(path, nrows=max_samples)
    # El dataset Enron tiene columnas "file" y "message"
    if "message" not in df.columns:
        print(f"  ⚠ Formato no reconocido: {list(df.columns)}")
        return pd.DataFrame()

    rows = []
    for _, row in df.iterrows():
        try:
            msg     = email.message_from_string(str(row["message"]))
            subject = str(msg.get("subject", ""))
            from_   = str(msg.get("from", ""))
            body    = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode("utf-8", errors="ignore")[:2000]
                        break
            else:
                body = str(msg.get_payload())[:2000]
            rows.append({"from": from_, "subject": subject, "body": body,
                            "auth_results": "", "label": 0, "phishing_type": "legitimate"})
        except Exception:
            pass

    df_enron = pd.DataFrame(rows)
    print(f"  ✓ Enron: {len(df_enron)} correos legítimos")
    return df_enron


def prepare_dataset():
    """Pipeline principal de preparación del dataset."""
    print("=" * 60)
    print("Sentryx v2 — Preparación de dataset de phishing por correo")
    print("=" * 60)

    frames = []

    # 1. Nazario
    nazario = load_nazario(RAW_DIR / "nazario_phishing.csv")
    if not nazario.empty:
        frames.append(nazario)

    # 2. SpamAssassin
    sa = load_spamassassin(RAW_DIR / "spamassassin_spam", RAW_DIR / "spamassassin_ham")
    if not sa.empty:
        frames.append(sa)

    # 3. Enron (legítimos)
    enron = load_enron(RAW_DIR / "enron_emails.csv")
    if not enron.empty:
        frames.append(enron)

    if not frames:
        print("\n⚠ No se encontraron datasets reales.")
        print("  Usando el dataset sintético generado para desarrollo.")
        synth = Path(PROCESSED_DIR / "emails_dataset.csv")
        if synth.exists():
            df = pd.read_csv(synth)
            print(f"  Dataset sintético cargado: {len(df)} muestras")
            return df
        else:
            print("  ERROR: Ejecutar primero el generador de datos sintéticos.")
            return None

    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset=["body"])
    df = df.dropna(subset=["body"])
    df = df[df["body"].str.len() > 20]
    df = df.sample(frac=1, random_state=42).reset_index(drop=True)

    # Balancear: máx 2:1 phishing:legítimo
    n_phish = df[df["label"] == 1].shape[0]
    n_legit = min(df[df["label"] == 0].shape[0], n_phish * 2)
    df_phish = df[df["label"] == 1]
    df_legit = df[df["label"] == 0].sample(n=n_legit, random_state=42)
    df       = pd.concat([df_phish, df_legit]).sample(frac=1, random_state=42).reset_index(drop=True)

    # Seudonimización del remitente — Ley 1581/2012
    import hashlib
    SALT = "sentryx-training-salt-2026"
    df["sender_hash"] = df["from"].apply(
        lambda x: hashlib.sha256(f"{x}{SALT}".encode()).hexdigest()[:16]
    )
    df = df.drop(columns=["from"])

    out_path = PROCESSED_DIR / "emails_dataset_real.csv"
    df.to_csv(out_path, index=False)

    print(f"\n✓ Dataset procesado: {len(df)} muestras")
    print(f"  Phishing: {df[df['label']==1].shape[0]}")
    print(f"  Legítimo: {df[df['label']==0].shape[0]}")
    print(f"  Guardado: {out_path}")

    print(f"\nDistribución por tipo:")
    print(df["phishing_type"].value_counts().to_string())

    return df


if __name__ == "__main__":
    prepare_dataset()
