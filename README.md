# Sentryx v2

Plataforma XDR open-source para detección de phishing por correo electrónico en empresas de e-commerce y retail.

> Proyecto de grado · Ingeniería de Software · Universidad Manuela Beltrán · 2026

---

## Tipos de phishing detectados

Siete tipos, cada uno con su sub-técnica de MITRE ATT&CK v14 (T1566.001 Attachment, .002 Link, .003 via Service, .004 Voice).

| Tipo | Descripción | MITRE |
|---|---|---|
| Spear phishing | Dirigido a persona específica | T1566.001 |
| Whaling | Dirigido a ejecutivos (CEO, CFO) | T1566.001 |
| BEC | Suplantación de correo corporativo | T1566.002 |
| Clone phishing | Copia de correo legítimo con enlaces reemplazados | T1566.001 |
| Vishing por correo | Solicita llamar a número falso | T1566.004 |
| Smishing por correo | Redirige a SMS/WhatsApp | T1566.003 |
| Genérico | Phishing masivo sin personalización | T1566.001 |

## Arquitectura ML — ensemble de tres modelos

```
Encabezados (35%)  →  Random Forest (SPF, DKIM, DMARC, typosquatting)
Contenido   (40%)  →  TF-IDF + LinearSVC (cuerpo, asunto, tipo de phishing)
URLs        (25%)  →  Random Forest (URLs embebidas en el correo)
                   ↓
              Score final 0–100
              legitimate | suspicious | phishing | critical
```

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| Backend | Python 3.11 · Django 4.2 · Django REST Framework |
| ML Engine | FastAPI · Scikit-learn · TF-IDF · NLTK · BeautifulSoup4 |
| Frontend | React 18 · Vite · Tailwind CSS |
| Base de datos | PostgreSQL 16 |
| Caché / Colas | Redis 7 · Celery |
| Threat Intel | MISP · PhishTank · OpenPhish · VirusTotal API |
| Infraestructura | Docker Compose · Nginx |

## Inicio rápido

```bash
git clone https://github.com/<org>/sentryx.git
cd sentryx
bash scripts/dev/setup.sh
```

| Servicio | URL |
|---|---|
| Dashboard | http://localhost |
| API REST | http://localhost/api/v1/ |
| API docs (OpenAPI / Swagger) | http://localhost/api/v1/docs/ |
| ML Engine docs | http://localhost/ml/docs |
| Django Admin | http://localhost/admin/ |
| Flower | http://localhost:5555 |

Credenciales de desarrollo: `admin@sentryx.local` / `admin123` y `analista@sentryx.local` / `analista123`.

Para actualizar una instalación anterior, compara tu `.env` con [`.env.example`](.env.example):
`setup.sh` avisa de las variables que faltan (por ejemplo `MFA_ENCRYPTION_KEY`).

## Seguridad y tareas programadas

- **Verificación en dos pasos (TOTP)** compatible con Google Authenticator y Microsoft
  Authenticator: se activa en *Seguridad de la cuenta*. Con `MFA_REQUIRED_FOR_ADMINS=True`
  los administradores deben activarla antes de usar el sistema.
- **Celery Beat** (hora de Bogotá), registrado por migración:
  purga diaria a las 02:00 (alertas cerradas a 90 días, auditoría a 365),
  PhishTank cada hora, OpenPhish cada 6 horas y reentrenamiento mensual
  (día 1, 03:00) si hay al menos `ML_RETRAIN_MIN_SAMPLES` correcciones.
- **Extensión de navegador** para Gmail y Outlook: ver [extension/README.md](extension/README.md).

## Estructura del repositorio

```
sentryx/
├── backend/                  # Django REST API + Celery
│   └── apps/
│       ├── alerts/           # Modelo Alert con PhishingType y Campaign
│       ├── incidents/        # Gestión de incidentes
│       ├── threat_intel/     # IOCs especializados en phishing
│       ├── audit/            # Log inmutable (Ley 1581/2012)
│       └── users/            # RBAC: admin, analyst, viewer
├── ml_engine/                # FastAPI + ensemble de tres modelos
│   └── pipelines/
│       ├── email_headers.py  # Random Forest — SPF, DKIM, typosquatting
│       ├── email_content.py  # TF-IDF + SVM — cuerpo y clasificación por tipo
│       ├── email_urls.py     # Random Forest — URLs embebidas
│       └── ensemble.py       # Voting ponderado 35/40/25
├── frontend/                 # React + Vite
├── extension/                # Extensión Manifest V3 para Gmail y Outlook (ver extension/README.md)
├── threat_intel/
│   └── rules/sigma/          # Reglas SIGMA de correlación
├── infra/                    # Nginx, PostgreSQL, Redis
├── docs/                     # ERS, arquitectura, API
└── scripts/dev/              # Setup automático del entorno
```

## Comandos frecuentes

```bash
make setup          # Setup inicial (primera vez)
make up             # Levantar todos los servicios
make test           # Correr todos los tests
make test-ml        # Tests solo del ML Engine
make test-backend   # Tests solo del backend
make logs           # Ver logs en tiempo real
make down           # Detener servicios
```

## Estándares aplicados

- ISO/IEC 12207:2017 — ciclo de vida del software
- NIST CSF v2.0 — funciones Identificar, Proteger, Detectar, Responder
- MITRE ATT&CK v14 — sub-técnicas T1566.001 – T1566.004
- Ley 1581 de 2012 (Colombia) — seudonimización de remitentes y destinatarios

## Licencia

Copyright 2026 Dany Vanesa Lugo Escobar y Juan Sebastián López Solórzano.

Sentryx se distribuye bajo la [Licencia Apache 2.0](LICENSE). Puedes usar,
modificar y redistribuir el código, incluso con fines comerciales, siempre que
conserves el aviso de copyright, incluyas una copia de la licencia y el archivo
[NOTICE](NOTICE), e indiques los cambios que hiciste en los archivos modificados.
La licencia incluye una concesión expresa de patentes y se entrega sin garantías.
