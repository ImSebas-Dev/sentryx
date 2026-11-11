#!/usr/bin/env python3
"""
Sentryx v2 — Genera un .env a partir de .env.example con secretos aleatorios.

Uso:
    python scripts/dev/generate_env.py                 # desarrollo (no sobrescribe)
    python scripts/dev/generate_env.py --production --domain sentryx.miempresa.co
    python scripts/dev/generate_env.py --output .env.nuevo --force

Cada ejecución genera claves nuevas: nunca reutilices las de .env.example ni las
de otra instalación. No imprime los secretos por pantalla.
"""
import argparse
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Variables que se rellenan con un valor aleatorio fuerte
SECRET_VARS = {
    "DJANGO_SECRET_KEY":      lambda: secrets.token_urlsafe(64),
    "POSTGRES_PASSWORD":      lambda: secrets.token_urlsafe(32),
    "REDIS_PASSWORD":         lambda: secrets.token_urlsafe(32),
    "ML_ENGINE_API_KEY":      lambda: secrets.token_urlsafe(48),
    "PSEUDONYMIZATION_SALT":  lambda: secrets.token_urlsafe(48),
    "MFA_ENCRYPTION_KEY":     lambda: secrets.token_urlsafe(48),
    "PAYMENT_SHIELD_SECRET":  lambda: secrets.token_urlsafe(48),
    "COMMUNITY_DB_PASSWORD":  lambda: secrets.token_urlsafe(32),
}


def build(example: str, production: bool, domain: str) -> str:
    values = {name: make() for name, make in SECRET_VARS.items()}
    redis_pwd = values["REDIS_PASSWORD"]
    values.update({
        "REDIS_URL":             f"redis://:{redis_pwd}@redis:6379/0",
        "CELERY_BROKER_URL":     f"redis://:{redis_pwd}@redis:6379/0",
        "CELERY_RESULT_BACKEND": f"redis://:{redis_pwd}@redis:6379/1",
    })
    if production:
        values.update({
            "ENVIRONMENT":            "production",
            "DJANGO_DEBUG":           "False",
            "DJANGO_SETTINGS_MODULE": "config.settings.production",
            "DJANGO_ALLOWED_HOSTS":   domain,
            "CORS_ALLOWED_ORIGINS":   f"https://{domain}",
            "CSRF_TRUSTED_ORIGINS":   f"https://{domain}",
            "FRONTEND_URL":           f"https://{domain}",
            "COOKIE_SECURE":          "True",
            "MFA_REQUIRED_FOR_ADMINS": "True",
            # Ruta del panel de Django difícil de adivinar
            "DJANGO_ADMIN_URL":       f"gestion-{secrets.token_hex(4)}/",
        })

    lines = []
    for line in example.splitlines():
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
        if key in values:
            lines.append(f"{key}={values[key]}")
        else:
            lines.append(line)
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--production", action="store_true")
    parser.add_argument("--domain", default="", help="Dominio público (obligatorio con --production)")
    parser.add_argument("--output", default=str(ROOT / ".env"))
    parser.add_argument("--force", action="store_true", help="Sobrescribir si ya existe")
    args = parser.parse_args()

    if args.production and not args.domain:
        sys.exit("Con --production indica --domain (p. ej. sentryx.miempresa.co).")
    output = Path(args.output)
    if output.exists() and not args.force:
        sys.exit(f"{output} ya existe. Usa --force o --output para escribir en otro archivo.")

    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    output.write_text(build(example, args.production, args.domain), encoding="utf-8")
    try:
        output.chmod(0o600)  # solo el dueño puede leerlo
    except OSError:
        pass
    print(f"Escrito {output} con secretos nuevos ({', '.join(SECRET_VARS)}).")


if __name__ == "__main__":
    main()
