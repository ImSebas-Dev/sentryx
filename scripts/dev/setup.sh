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

# ── 2. Generar .env con secretos aleatorios ──────────────
# Antes se escribían claves fijas publicadas en el repositorio: cualquiera que
# lo hubiera visto conocía la SECRET_KEY y las contraseñas de BD y Redis.
if [ -f ".env" ]; then
  warn ".env ya existe — no se sobreescribe."
else
  info "Generando .env con secretos nuevos..."
  python3 scripts/dev/generate_env.py
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
# Contraseñas aleatorias: admin123/analista123 estaban publicadas en el README.
ADMIN_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(12))")
ANALYST_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(12))")
info "Creando usuario administrador..."
$COMPOSE_CMD -f docker-compose.yml -f docker-compose.dev.yml run --rm -e SEED_PASSWORD="$ADMIN_PASSWORD" backend \
  python manage.py shell -c "
import os
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(email='admin@sentryx.local').exists():
    u = User.objects.create_superuser('admin', 'admin@sentryx.local', os.environ['SEED_PASSWORD'], role='admin', organization='Sentryx Demo')
    u.is_email_verified = True
    u.accepted_terms = True
    u.save()
    print('Admin creado')
else:
    User.objects.filter(email='admin@sentryx.local').update(
        is_email_verified=True, accepted_terms=True
    )
    print('Admin ya existe — actualizado (su contraseña NO se cambió)')
"
success "Admin listo"

# ── 7. Crear usuario analista ─────────────────────────────
info "Creando usuario analista..."
$COMPOSE_CMD -f docker-compose.yml -f docker-compose.dev.yml run --rm -e SEED_PASSWORD="$ANALYST_PASSWORD" backend \
  python manage.py shell -c "
import os
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(email='analista@sentryx.local').exists():
    u = User.objects.create_user('analista', 'analista@sentryx.local', os.environ['SEED_PASSWORD'], role='analyst', organization='Sentryx Demo')
    u.is_email_verified = True
    u.accepted_terms = True
    u.save()
    print('Analista creado')
else:
    User.objects.filter(email='analista@sentryx.local').update(
        is_email_verified=True, accepted_terms=True
    )
    print('Analista ya existe — actualizado (su contraseña NO se cambió)')
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
echo -e "  ${GREEN}ML Engine docs${NC}   →  http://127.0.0.1:8001/docs (solo desarrollo)"
echo -e "  ${GREEN}Django Admin${NC}     →  http://localhost/admin/"
echo -e "  ${GREEN}Flower (Celery)${NC}  →  http://localhost:5555"
echo ""
echo -e "  ${BOLD}Credenciales:${NC}"
echo -e "  Email:      admin@sentryx.local"
echo -e "  Contraseña: ${ADMIN_PASSWORD}  (solo si se acaba de crear)"
echo ""
echo -e "  Email:      analista@sentryx.local"
echo -e "  Contraseña: ${ANALYST_PASSWORD}  (solo si se acaba de crear)"
echo ""
echo -e "  Verificación en dos pasos: actívala en Dashboard → Seguridad de la cuenta."
echo -e "  Extensión de navegador:   ver extension/README.md"
echo ""
