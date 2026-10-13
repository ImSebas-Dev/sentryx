#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════
#  Sentryx v2 — Setup inicial del entorno de desarrollo
#  Uso: bash scripts/dev/setup.sh
#  Tiempo estimado: 3-5 minutos la primera vez
# ══════════════════════════════════════════════════════════
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}  $1"; }
success() { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║      Sentryx v2 — Setup inicial         ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${NC}"
echo ""

# ── 1. Verificar dependencias ─────────────────────────────
info "Verificando dependencias..."
command -v docker  >/dev/null 2>&1 || error "Docker no instalado."
command -v python3 >/dev/null 2>&1 || error "Python 3 no instalado."

COMPOSE_CMD=""
if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD="docker-compose"
else
  error "Docker Compose no encontrado."
fi
success "Docker OK | Compose: $COMPOSE_CMD"

# ── 2. Generar .env con claves fijas (para desarrollo) ───
if [ -f ".env" ]; then
  warn ".env ya existe — no se sobreescribe."
else
  info "Generando .env..."
  cat > .env << 'ENVEOF'
ENVIRONMENT=development
DJANGO_SECRET_KEY=sentryx-dev-secret-key-2026-cambiar-en-produccion
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,backend
DJANGO_SETTINGS_MODULE=config.settings.development
POSTGRES_DB=sentryx
POSTGRES_USER=sentryx
POSTGRES_PASSWORD=sentryx123
POSTGRES_HOST=db
POSTGRES_PORT=5432
REDIS_PASSWORD=redis123
REDIS_URL=redis://:redis123@redis:6379/0
CELERY_BROKER_URL=redis://:redis123@redis:6379/0
CELERY_RESULT_BACKEND=redis://:redis123@redis:6379/1
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_LIFETIME_MINUTES=60
JWT_REFRESH_TOKEN_LIFETIME_DAYS=1
MFA_ENCRYPTION_KEY=sentryx-dev-mfa-key-2026-cambiar-en-produccion
MFA_REQUIRED_FOR_ADMINS=False
THROTTLE_MFA_RATE=10/min
ML_ENGINE_URL=http://ml_engine:8001
ML_ENGINE_API_KEY=mlkey123
ML_THRESHOLD_SUSPICIOUS=40
ML_THRESHOLD_PHISHING=70
ML_THRESHOLD_CRITICAL=85
ML_WEIGHT_HEADERS=0.35
ML_WEIGHT_CONTENT=0.40
ML_WEIGHT_URLS=0.25
ML_RETRAIN_MIN_SAMPLES=5
PSEUDONYMIZATION_SALT=salt-unico-sentryx-2026
DATA_RETENTION_EVENT_LOGS_DAYS=90
DATA_RETENTION_INCIDENTS_DAYS=365
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://localhost
SENDGRID_API_KEY=
SENDGRID_FROM_EMAIL=noreply@sentryx.com
FRONTEND_URL=http://localhost
AXES_FAILURE_LIMIT=5
AXES_COOLOFF_TIME=1
PHISHTANK_API_KEY=
PHISHTANK_SYNC_INTERVAL_HOURS=1
OPENPHISH_FEED_URL=https://openphish.com/feed.txt
OPENPHISH_SYNC_INTERVAL_HOURS=6
ENVEOF
  success ".env generado"
fi

# Un .env anterior no se sobrescribe: avisar de las variables nuevas que le
# faltan (p. ej. MFA_ENCRYPTION_KEY). No editarlo aquí: puede tener secretos reales.
if [ -f ".env.example" ]; then
  MISSING=$(grep -oE '^[A-Z_]+=' .env.example | tr -d '=' | while read -r var; do
    grep -qE "^${var}=" .env || echo "$var"
  done)
  if [ -n "$MISSING" ]; then
    warn "Tu .env no tiene estas variables de .env.example (cópialas con su valor):"
    for var in $MISSING; do echo "         - $var"; done
  fi
fi

# ── 3. Construir imágenes ─────────────────────────────────
info "Construyendo imágenes Docker (2-3 min la primera vez)..."
$COMPOSE_CMD -f docker-compose.yml -f docker-compose.dev.yml build --quiet
success "Imágenes construidas"

# ── 4. Levantar PostgreSQL y Redis ────────────────────────
info "Iniciando PostgreSQL y Redis..."
$COMPOSE_CMD up -d db redis
echo -n "   Esperando BD"
for i in $(seq 1 30); do
  if $COMPOSE_CMD exec -T db pg_isready -U sentryx >/dev/null 2>&1; then
    echo " ✓"; break
  fi
  echo -n "."; sleep 2
done
success "PostgreSQL listo"

# ── 5. Migraciones ────────────────────────────────────────
# Incluye alerts/0005, que registra en Celery Beat la purga diaria, la
# sincronización de PhishTank/OpenPhish y el reentrenamiento mensual.
info "Aplicando migraciones..."
$COMPOSE_CMD -f docker-compose.yml -f docker-compose.dev.yml run --rm backend \
  python manage.py migrate --noinput
success "Migraciones aplicadas"

# ── 6. Crear usuario admin ────────────────────────────────
info "Creando usuario administrador..."
$COMPOSE_CMD -f docker-compose.yml -f docker-compose.dev.yml run --rm backend \
  python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(email='admin@sentryx.local').exists():
    u = User.objects.create_superuser('admin', 'admin@sentryx.local', 'admin123', role='admin')
    u.is_email_verified = True
    u.is_approved = True
    u.accepted_terms = True
    u.save()
    print('Admin creado')
else:
    User.objects.filter(email='admin@sentryx.local').update(
        is_email_verified=True, is_approved=True, accepted_terms=True
    )
    print('Admin ya existe — actualizado')
"
success "Admin listo"

# ── 7. Crear usuario analista ─────────────────────────────
info "Creando usuario analista..."
$COMPOSE_CMD -f docker-compose.yml -f docker-compose.dev.yml run --rm backend \
  python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(email='analista@sentryx.local').exists():
    u = User.objects.create_user('analista', 'analista@sentryx.local', 'analista123', role='analyst')
    u.is_email_verified = True
    u.is_approved = True
    u.accepted_terms = True
    u.save()
    print('Analista creado')
else:
    User.objects.filter(email='analista@sentryx.local').update(
        is_email_verified=True, is_approved=True, accepted_terms=True
    )
    print('Analista ya existe — actualizado')
"
success "Analista listo"

# ── 8. Levantar todos los servicios ──────────────────────
info "Levantando todos los servicios..."
$COMPOSE_CMD -f docker-compose.yml -f docker-compose.dev.yml up -d
success "Servicios en ejecución"
echo -n "   Esperando backend"
for i in $(seq 1 30); do
  if $COMPOSE_CMD -f docker-compose.yml -f docker-compose.dev.yml exec -T backend \
       curl -sf http://localhost:8000/api/v1/health/ >/dev/null 2>&1; then
    echo " ✓"; break
  fi
  echo -n "."; sleep 2
done

# ── 9. Verificar tareas programadas ─────────────────────
info "Tareas programadas registradas en Celery Beat:"
$COMPOSE_CMD -f docker-compose.yml -f docker-compose.dev.yml exec -T backend \
  python manage.py shell -c "
from django_celery_beat.models import PeriodicTask
for t in PeriodicTask.objects.exclude(name__startswith='celery.').order_by('name'):
    print(f'         - {t.name:18} {t.task}')
" 2>/dev/null | grep -- '- ' || warn "No se pudieron listar (revisa: make logs-backend)"

# ── 10. Resumen ──────────────────────────────────────────
sleep 10
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════${NC}"
echo -e "${BOLD}  Sentryx v2 — Listo para usar${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${GREEN}Dashboard${NC}        →  http://localhost"
echo -e "  ${GREEN}API REST${NC}         →  http://localhost/api/v1/"
echo -e "  ${GREEN}API docs (OpenAPI)${NC} →  http://localhost/api/v1/docs/"
echo -e "  ${GREEN}ML Engine docs${NC}   →  http://localhost/ml/docs"
echo -e "  ${GREEN}Django Admin${NC}     →  http://localhost/admin/"
echo -e "  ${GREEN}Flower (Celery)${NC}  →  http://localhost:5555"
echo ""
echo -e "  ${BOLD}Credenciales:${NC}"
echo -e "  Email:      admin@sentryx.local"
echo -e "  Contraseña: admin123"
echo ""
echo -e "  Email:      analista@sentryx.local"
echo -e "  Contraseña: analista123"
echo ""
echo -e "  Verificación en dos pasos: actívala en Dashboard → Seguridad de la cuenta."
echo -e "  Extensión de navegador:   ver extension/README.md"
echo ""
