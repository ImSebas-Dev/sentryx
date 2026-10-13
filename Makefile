# ══════════════════════════════════════════════════════════
#  Sentryx v2 — Makefile
# ══════════════════════════════════════════════════════════
.PHONY: help up down build logs test test-ml test-backend migrate \
        shell createsuperuser db-shell train setup lint

DC     = docker compose
DC_DEV = docker compose -f docker-compose.yml -f docker-compose.dev.yml
BE     = $(DC_DEV) exec backend
ML     = $(DC_DEV) exec ml_engine

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Ciclo de vida ─────────────────────────────────────────
setup: ## Setup inicial del entorno (primera vez)
	bash scripts/dev/setup.sh

up: ## Levantar todos los servicios en modo desarrollo
	$(DC_DEV) up -d
	@echo ""
	@echo "  Dashboard  → http://localhost"
	@echo "  API        → http://localhost/api/v1/"
	@echo "  ML Docs    → http://localhost/ml/docs"
	@echo "  Admin      → http://localhost/admin/"
	@echo "  Flower     → http://localhost:5555"

down: ## Detener todos los servicios
	$(DC) down

build: ## Reconstruir imágenes
	$(DC) build --no-cache

logs: ## Logs de todos los servicios
	$(DC_DEV) logs -f

logs-backend: ## Logs del backend
	$(DC_DEV) logs -f backend

logs-ml: ## Logs del ML Engine
	$(DC_DEV) logs -f ml_engine

# ── Tests ─────────────────────────────────────────────────
test: ## Correr todos los tests (backend + ML)
	@echo "── Backend ──"
	$(BE) pytest --cov=. --cov-report=term-missing -q
	@echo "\n── ML Engine ──"
	$(ML) pytest --cov=. --cov-report=term-missing -q

test-backend: ## Tests solo del backend con detalle
	$(BE) pytest --cov=. --cov-report=term-missing -v

test-ml: ## Tests solo del ML Engine
	$(ML) pytest --cov=. --cov-report=term-missing -v

test-fast: ## Tests rápidos (sin marcados slow)
	$(BE) pytest -m "not slow" -q
	$(ML) pytest -m "not slow" -q

# ── Django ────────────────────────────────────────────────
migrate: ## Correr migraciones
	$(BE) python manage.py migrate

makemigrations: ## Crear migraciones (uso: make makemigrations app=alerts)
	$(BE) python manage.py makemigrations $(app)

shell: ## Django shell
	$(BE) python manage.py shell

createsuperuser: ## Crear superusuario
	$(BE) python manage.py createsuperuser

setup-beat: ## Configurar tareas Celery Beat
	$(BE) python manage.py shell < scripts/db/setup_celery_beat.py

# ── ML ────────────────────────────────────────────────────
train: ## Entrenar los tres modelos ML
	$(ML) python /scripts/ml/train_models.py

prepare-data: ## Preparar dataset de entrenamiento
	$(ML) python /scripts/ml/prepare_dataset.py

# ── BD ────────────────────────────────────────────────────
db-shell: ## psql interactivo
	$(DC) exec db psql -U sentryx -d sentryx

db-reset: ## ⚠ Borrar y recrear BD (pierde datos)
	@echo "⚠ Esto borrará TODOS los datos. ENTER para continuar, Ctrl+C para cancelar."
	@read _
	$(DC) down -v
	$(DC_DEV) up -d db redis
	sleep 5
	$(DC_DEV) up -d backend
	$(BE) python manage.py migrate

# ── Linting ───────────────────────────────────────────────
lint: ## Linting Python y JavaScript
	$(BE) flake8 . --max-line-length=100 --exclude=migrations/
	$(ML) flake8 . --max-line-length=100
	$(DC_DEV) exec frontend npm run lint

clean: ## Limpiar contenedores y volúmenes
	$(DC) down -v --remove-orphans
