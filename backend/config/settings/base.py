"""Sentryx v2 — Django settings base (phishing por correo)."""
from pathlib import Path
from decouple import config, Csv
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY     = config("DJANGO_SECRET_KEY")
DEBUG          = config("DJANGO_DEBUG", default=False, cast=bool)
ALLOWED_HOSTS  = config("DJANGO_ALLOWED_HOSTS", default="localhost", cast=Csv())

# ── Apps ──────────────────────────────────────────────────
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    # Lista negra de refresh tokens: sin esta app BLACKLIST_AFTER_ROTATION no
    # hace nada y un refresh robado o ya usado seguía sirviendo hasta caducar.
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "axes",
    "django_celery_beat",
    "django_celery_results",
    "drf_spectacular",
    "drf_spectacular_sidecar",
]

LOCAL_APPS = [
    "apps.users",
    "apps.alerts",
    "apps.incidents",
    "apps.threat_intel",
    "apps.audit",
    "apps.ml_feedback",
    "apps.payment_shield",
    "apps.four_eyes",
    "apps.response",
    "apps.community",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ── Middleware ────────────────────────────────────────────
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "axes.middleware.AxesMiddleware",
    "apps.audit.middleware.AuditLogMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF      = "config.urls"
WSGI_APPLICATION  = "config.wsgi.application"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug",
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]

# ── Base de datos ─────────────────────────────────────────
DATABASES = {"default": {
    "ENGINE":   "django.db.backends.postgresql",
    "NAME":     config("POSTGRES_DB",       default="sentryx"),
    "USER":     config("POSTGRES_USER",     default="sentryx"),
    "PASSWORD": config("POSTGRES_PASSWORD", default=""),
    "HOST":     config("POSTGRES_HOST",     default="db"),
    "PORT":     config("POSTGRES_PORT",     default="5432"),
    "CONN_MAX_AGE": config("POSTGRES_CONN_MAX_AGE", default=60, cast=int),
    "CONN_HEALTH_CHECKS": True,
    "OPTIONS":  {
        "options": "-c timezone=America/Bogota -c statement_timeout=30000",
        # "require" o "verify-full" si la base de datos está en otra máquina
        "sslmode": config("POSTGRES_SSLMODE", default="prefer"),
    },
}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Caché Redis ───────────────────────────────────────────
CACHES = {"default": {
    "BACKEND":  "django_redis.cache.RedisCache",
    "LOCATION": config("REDIS_URL", default="redis://redis:6379/0"),
    "OPTIONS":  {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
}}

# ── Celery ────────────────────────────────────────────────
CELERY_BROKER_URL        = config("CELERY_BROKER_URL")
CELERY_RESULT_BACKEND    = config("CELERY_RESULT_BACKEND")
CELERY_ACCEPT_CONTENT    = ["json"]
CELERY_TASK_SERIALIZER   = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE          = "America/Bogota"
CELERY_BEAT_SCHEDULER    = "django_celery_beat.schedulers:DatabaseScheduler"

# ── Auth ──────────────────────────────────────────────────
AUTH_USER_MODEL = "users.ShieldUser"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Argon2id para las contraseñas nuevas. PBKDF2 queda para leer los hashes
# antiguos: Django los vuelve a guardar con Argon2 en el siguiente login.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

# ── JWT ───────────────────────────────────────────────────
# El access token vive solo en memoria del navegador: que dure poco. El
# refresh viaja en una cookie HttpOnly (ver apps/users/cookies.py).
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME":    timedelta(minutes=config("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", default=15, cast=int)),
    "REFRESH_TOKEN_LIFETIME":   timedelta(days=config("JWT_REFRESH_TOKEN_LIFETIME_DAYS", default=1, cast=int)),
    "ALGORITHM":                config("JWT_ALGORITHM", default="HS256"),
    "AUTH_HEADER_TYPES":        ("Bearer",),
    "ROTATE_REFRESH_TOKENS":    True,
    "BLACKLIST_AFTER_ROTATION": True,
}

# ── DRF ───────────────────────────────────────────────────
REST_FRAMEWORK = {
    # ShieldJWTAuthentication = JWTAuthentication + bloqueo de los tokens con
    # mfa_setup_required (admins sin 2FA cuando MFA_REQUIRED_FOR_ADMINS=True).
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.users.authentication.ShieldJWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Solo JSON: la API navegable de DRF queda para desarrollo (development.py)
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    # El cupo es por usuario y compartido por TODOS los endpoints (incluidos
    # el polling del dashboard y la extensión), por eso no puede ser muy bajo.
    # Los anónimos (login, registro) se cuentan por IP real del cliente.
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": config("THROTTLE_ANON_RATE", default="300/hour"),
        "user": config("THROTTLE_USER_RATE", default="1000/hour"),
        # Login con contraseña y renovación del token, por IP
        "auth_login":   config("THROTTLE_AUTH_LOGIN_RATE",   default="10/min"),
        "auth_refresh": config("THROTTLE_AUTH_REFRESH_RATE", default="60/min"),
        # Registro y correos (verificación, recuperación): evita spam de correos
        "auth_register": config("THROTTLE_AUTH_REGISTER_RATE", default="10/hour"),
        "auth_email":    config("THROTTLE_AUTH_EMAIL_RATE",    default="5/hour"),
        # Análisis de correos: llama al motor ML, que es lo más costoso
        "analyze": config("THROTTLE_ANALYZE_RATE", default="300/hour"),
        # Endpoints de 2FA: se cuenta por IP (anónimos) o por usuario
        "mfa":  config("THROTTLE_MFA_RATE",  default="10/min"),
        # Polling de la extensión: un correo abierto consulta cada 20 s (180/hora)
        "four_eyes_status": config("THROTTLE_FOUR_EYES_STATUS_RATE", default="360/hour"),
    },
    # nginx añade la IP del cliente al final de X-Forwarded-For; con 1 proxy
    # DRF usa esa entrada (no falsificable) en lugar de la IP de nginx.
    "NUM_PROXIES": 1,
}

# ── OpenAPI (drf-spectacular) ─────────────────────────────
# /api/v1/schema/ y /api/v1/docs/. Con DEBUG=False solo usuarios autenticados:
# por sesión (entrar antes en /admin/) o con "Authorization: Bearer <token>".
SPECTACULAR_SETTINGS = {
    "TITLE": "Sentryx API",
    "DESCRIPTION": (
        "API REST de Sentryx v2, plataforma XDR de detección de phishing por correo.\n\n"
        "Autenticación: `POST /api/v1/auth/token/` con correo y contraseña. Si la cuenta "
        "tiene verificación en dos pasos, la respuesta trae `mfa_required` y `mfa_token`, "
        "que se canjean en `POST /api/v1/auth/mfa/verify/`. Enviar el token de acceso en "
        "`Authorization: Bearer <access>`."
    ),
    "VERSION": "2.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SERVE_PERMISSIONS": ["apps.users.permissions.IsAuthenticatedUnlessDebug"],
    # JWT primero: sin credenciales responde 401 con WWW-Authenticate: Bearer
    "SERVE_AUTHENTICATION": [
        "apps.users.authentication.ShieldJWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "SWAGGER_UI_SETTINGS": {"persistAuthorization": True, "displayRequestDuration": True},
    "COMPONENT_SPLIT_REQUEST": True,
    # Varios modelos tienen un campo "status": dar a cada enum un nombre propio
    "ENUM_NAME_OVERRIDES": {
        "SeverityEnum":            "apps.alerts.models.Alert.Severity",
        "AlertStatusEnum":         "apps.alerts.models.Alert.Status",
        "IncidentStatusEnum":      "apps.incidents.models.Incident.Status",
        "RetrainingJobStatusEnum": "apps.ml_feedback.models.RetrainingJob.Status",
        "FeedbackStatusEnum":      "apps.ml_feedback.models.TrainingFeedback.Status",
        "PaymentCheckStatusEnum":  "apps.payment_shield.models.PaymentCheck.Status",
        "ApprovalStatusEnum":      "apps.four_eyes.models.ApprovalRequest.Status",
        "ResponseSessionStatusEnum": "apps.response.models.ResponseSession.Status",
    },
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "TAGS": [
        {"name": "auth",         "description": "Login, registro, perfil y recuperación de contraseña"},
        {"name": "mfa",          "description": "Verificación en dos pasos (TOTP)"},
        {"name": "alerts",       "description": "Análisis de correos, alertas y campañas"},
        {"name": "reports",      "description": "Informes semanales y mensuales (PDF/CSV)"},
        {"name": "incidents",    "description": "Gestión de incidentes"},
        {"name": "threat-intel", "description": "Indicadores de compromiso (IOC)"},
        {"name": "ml",           "description": "Reentrenamiento del modelo"},
        {"name": "audit",        "description": "Log de auditoría (solo admin)"},
        {"name": "Escudo de pagos", "description": "Proveedores de confianza y validación de pagos y facturas DIAN"},
        {"name": "Cuatro ojos", "description": "Aprobación de una segunda persona para correos de alto riesgo"},
        {"name": "Respuesta a incidentes", "description": "Asistente de los primeros 15 minutos y paquete de denuncia"},
        {"name": "Red de alerta", "description": "Avisos tempranos entre pymes con opt-in; solo se comparten hashes"},
    ],
}

# ── django-axes ───────────────────────────────────────────
AXES_FAILURE_LIMIT      = config("AXES_FAILURE_LIMIT", default=5, cast=int)
AXES_COOLOFF_TIME       = config("AXES_COOLOFF_TIME",  default=1, cast=int)
AXES_LOCKOUT_PARAMETERS = ["username", "ip_address"]
AXES_RESET_ON_SUCCESS   = True
# El login envía "email" (USERNAME_FIELD). Con el valor por defecto
# ("username") axes no veía la cuenta y solo bloqueaba por IP.
AXES_USERNAME_FORM_FIELD = "email"
# Sin esto axes usaba REMOTE_ADDR, que detrás de nginx es la IP de nginx: cinco
# fallos de cualquier persona bloqueaban el login de todos los usuarios.
AXES_CLIENT_IP_CALLABLE = "apps.audit.utils.client_ip"
# La API envía "email" y el login de /admin/ "username": contar ambos
AXES_USERNAME_CALLABLE  = "apps.audit.utils.axes_username"

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# ── Autenticación de dos factores (TOTP) ──────────────────
# Clave para cifrar en reposo los secretos TOTP (Fernet). Si se cambia, los
# secretos guardados dejan de poder descifrarse y cada usuario debe volver a
# activar el 2FA. Sin valor, los endpoints de 2FA responden 503.
MFA_ENCRYPTION_KEY       = config("MFA_ENCRYPTION_KEY", default="")
MFA_REQUIRED_FOR_ADMINS  = config("MFA_REQUIRED_FOR_ADMINS", default=False, cast=bool)
MFA_ISSUER               = "Sentryx"
MFA_LOGIN_TOKEN_MAX_AGE  = 300   # segundos de validez del mfa_token
MFA_MAX_ATTEMPTS         = 5     # intentos de código por mfa_token
MFA_RECOVERY_CODES       = 8

# ── CORS ──────────────────────────────────────────────────
# Lista explícita de orígenes: nunca CORS_ALLOW_ALL_ORIGINS con credenciales.
# El frontend se sirve desde el mismo origen que la API (nginx o el proxy de
# Vite) y la extensión usa host_permissions, así que casi no hace falta CORS.
CORS_ALLOWED_ORIGINS   = config("CORS_ALLOWED_ORIGINS", default="http://localhost:5173", cast=Csv())
CORS_ALLOW_CREDENTIALS = True
CORS_URLS_REGEX        = r"^/api/.*$"
CORS_ALLOW_METHODS     = ["DELETE", "GET", "OPTIONS", "PATCH", "POST", "PUT"]
CORS_ALLOW_HEADERS     = ["accept", "authorization", "content-type", "x-sentryx-client"]
CORS_PREFLIGHT_MAX_AGE = 3600

# ── Privacidad — Ley 1581/2012 ────────────────────────────
PSEUDONYMIZATION_SALT               = config("PSEUDONYMIZATION_SALT")
DATA_RETENTION_EVENT_LOGS_DAYS      = config("DATA_RETENTION_EVENT_LOGS_DAYS", default=90,  cast=int)
DATA_RETENTION_INCIDENTS_DAYS       = config("DATA_RETENTION_INCIDENTS_DAYS",  default=365, cast=int)

# ── Motor ML (email phishing) ─────────────────────────────
ML_ENGINE_URL     = config("ML_ENGINE_URL",     default="http://ml_engine:8001")
ML_ENGINE_API_KEY = config("ML_ENGINE_API_KEY", default="")

ML_THRESHOLDS = {
    "suspicious": config("ML_THRESHOLD_SUSPICIOUS", default=40, cast=int),
    "phishing":   config("ML_THRESHOLD_PHISHING",   default=70, cast=int),
    "critical":   config("ML_THRESHOLD_CRITICAL",   default=85, cast=int),
}

ML_WEIGHTS = {
    "headers": config("ML_WEIGHT_HEADERS", default=0.35, cast=float),
    "content": config("ML_WEIGHT_CONTENT", default=0.40, cast=float),
    "urls":    config("ML_WEIGHT_URLS",    default=0.25, cast=float),
}

# Mínimo de correcciones pendientes para reentrenar (manual y mensual).
# Usar siempre este valor; no volver a escribir el número en las vistas.
ML_RETRAIN_MIN_SAMPLES = config("ML_RETRAIN_MIN_SAMPLES", default=5, cast=int)

# ── Threat Intelligence ───────────────────────────────────
MISP_URL        = config("MISP_URL",        default="")
MISP_API_KEY    = config("MISP_API_KEY",    default="")
MISP_VERIFY_SSL = config("MISP_VERIFY_SSL", default=True, cast=bool)

PHISHTANK_API_KEY              = config("PHISHTANK_API_KEY",              default="")
PHISHTANK_SYNC_INTERVAL_HOURS  = config("PHISHTANK_SYNC_INTERVAL_HOURS",  default=1, cast=int)

OPENPHISH_FEED_URL             = config("OPENPHISH_FEED_URL", default="https://openphish.com/feed.txt")
OPENPHISH_SYNC_INTERVAL_HOURS  = config("OPENPHISH_SYNC_INTERVAL_HOURS",  default=6, cast=int)

VIRUSTOTAL_API_KEY   = config("VIRUSTOTAL_API_KEY",        default="")
VIRUSTOTAL_RATE_LIMIT= config("VIRUSTOTAL_RATE_LIMIT_PER_MIN", default=4, cast=int)

# ── Escudo de pagos ───────────────────────────────────────
# Sin secreto el escudo sigue funcionando, pero no registra ni compara cuentas.
# Si cambias el secreto, vuelve a registrar las cuentas de los proveedores.
PAYMENT_SHIELD_SECRET            = config("PAYMENT_SHIELD_SECRET", default="")
PAYMENT_SHIELD_MAX_ATTACHMENT_MB = config("PAYMENT_SHIELD_MAX_ATTACHMENT_MB", default=5, cast=int)
PAYMENT_SHIELD_EXTRA_BANKS       = config("PAYMENT_SHIELD_EXTRA_BANKS", default="", cast=Csv())

# ── Control de cuatro ojos ────────────────────────────────
# La política se edita desde la interfaz; esto solo fija los valores iniciales.
FOUR_EYES_DEFAULT_EXPIRY_MINUTES = config("FOUR_EYES_DEFAULT_EXPIRY_MINUTES", default=240, cast=int)
FOUR_EYES_EXPIRY_CHECK_MINUTES   = config("FOUR_EYES_EXPIRY_CHECK_MINUTES", default=5, cast=int)

# ── Respuesta a incidentes ────────────────────────────────
# Enlace que se muestra para denunciar. Sentryx no envía nada automáticamente.
CAI_VIRTUAL_URL = config("CAI_VIRTUAL_URL", default="")

# ── Red de alerta entre pymes ─────────────────────────────
# Sin COMMUNITY_HUB_URL la red queda inactiva: el resto del sistema funciona igual.
COMMUNITY_HUB_URL      = config("COMMUNITY_HUB_URL", default="")
COMMUNITY_NODE_API_KEY = config("COMMUNITY_NODE_API_KEY", default="")
COMMUNITY_NETWORK_KEY  = config("COMMUNITY_NETWORK_KEY", default="")
COMMUNITY_SYNC_MINUTES = config("COMMUNITY_SYNC_MINUTES", default=15, cast=int)

# ── Estáticos ─────────────────────────────────────────────
STATIC_URL  = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# ── i18n ─────────────────────────────────────────────────
LANGUAGE_CODE = "es-co"
TIME_ZONE     = "America/Bogota"
USE_I18N      = True
USE_TZ        = True

# ── Seguridad HTTP ────────────────────────────────────────
# production.py activa HTTPS obligatorio, HSTS y cookies Secure.
SECURE_CONTENT_TYPE_NOSNIFF       = True
X_FRAME_OPTIONS                   = "DENY"
SECURE_REFERRER_POLICY            = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# Cookies de sesión (solo las usa /admin/) y CSRF
SESSION_COOKIE_HTTPONLY         = True
SESSION_COOKIE_SAMESITE         = "Lax"
SESSION_COOKIE_AGE              = config("SESSION_COOKIE_AGE", default=8 * 3600, cast=int)
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_SECURE           = config("COOKIE_SECURE", default=False, cast=bool)
CSRF_COOKIE_HTTPONLY            = True
CSRF_COOKIE_SAMESITE            = "Lax"
CSRF_COOKIE_SECURE              = SESSION_COOKIE_SECURE
CSRF_TRUSTED_ORIGINS            = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())

# Cookie del refresh token del panel web (apps/users/cookies.py). HttpOnly:
# el JavaScript de la página no puede leerla, así que un XSS no se la lleva.
AUTH_REFRESH_COOKIE_NAME   = "sentryx_refresh"
AUTH_REFRESH_COOKIE_PATH   = "/api/v1/auth/"
AUTH_REFRESH_COOKIE_SECURE = SESSION_COOKIE_SECURE
# Cabecera que el panel web envía en cada petición. Un sitio ajeno no puede
# añadirla sin pasar el preflight de CORS: es la defensa CSRF de los endpoints
# que leen la cookie (refresh y logout), junto con SameSite=Strict.
AUTH_WEB_CLIENT_HEADER = "HTTP_X_SENTRYX_CLIENT"

# ── Enlaces de los correos de cuenta ──────────────────────
EMAIL_VERIFICATION_TIMEOUT_HOURS = config("EMAIL_VERIFICATION_TIMEOUT_HOURS", default=24, cast=int)
PASSWORD_RESET_TIMEOUT_MINUTES   = config("PASSWORD_RESET_TIMEOUT_MINUTES",   default=30, cast=int)
# Espera mínima entre dos correos de verificación o recuperación a la misma cuenta
AUTH_EMAIL_COOLDOWN_SECONDS      = config("AUTH_EMAIL_COOLDOWN_SECONDS",      default=60, cast=int)

# ── Subida de archivos y tamaño de las peticiones ─────────
DATA_UPLOAD_MAX_MEMORY_SIZE   = 5 * 1024 * 1024   # cuerpo JSON/form sin contar archivos
FILE_UPLOAD_MAX_MEMORY_SIZE   = 5 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 200
DATA_UPLOAD_MAX_NUMBER_FILES  = 10
# Adjuntos aceptados en /alerts/analyze/: solo los que el sistema sabe leer
ANALYZE_ALLOWED_ATTACHMENT_EXTENSIONS = (".xml", ".zip")
ANALYZE_MAX_ATTACHMENTS               = 10

# ── Panel de administración de Django ─────────────────────
# Cambia la ruta en producción (p. ej. DJANGO_ADMIN_URL=gestion-7f3a/) y
# déjalo apagado si no lo usas (DJANGO_ADMIN_ENABLED=False).
ADMIN_ENABLED = config("DJANGO_ADMIN_ENABLED", default=True, cast=bool)
ADMIN_URL     = config("DJANGO_ADMIN_URL", default="admin/")

# ── Logs ──────────────────────────────────────────────────
# sentryx.security recibe logins fallidos, bloqueos, 401/403/429 y cambios
# sensibles. En producción envía la salida del contenedor a tu sistema de logs.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "[{levelname}] {asctime} {name} — {message}", "style": "{"},
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "verbose"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django":           {"handlers": ["console"], "level": "INFO",    "propagate": False},
        "django.security":  {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "sentryx.security": {"handlers": ["console"], "level": "INFO",    "propagate": False},
        "apps":             {"handlers": ["console"], "level": "INFO",    "propagate": False},
        "axes":             {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}

# ── SendGrid (correo transaccional) ──────────────────────
SENDGRID_API_KEY    = config("SENDGRID_API_KEY",    default="")
SENDGRID_FROM_EMAIL = config("SENDGRID_FROM_EMAIL", default="noreply@sentryx.com")

# URL pública del frontend (para construir enlaces en los correos)
FRONTEND_URL = config("FRONTEND_URL", default="http://localhost")

# Backend de email de Django (para uso interno de password reset de admin)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"