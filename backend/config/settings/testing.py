from .base import *  # noqa
from decouple import config

DEBUG = False

# Tomar host y credenciales del entorno para que las pruebas corran dentro
# del contenedor (host "db"). Django crea y borra "test_<NAME>" solo.
DATABASES = {"default": {
    "ENGINE":   "django.db.backends.postgresql",
    "NAME":     "sentryx_test",
    "USER":     config("POSTGRES_USER",     default="sentryx"),
    "PASSWORD": config("POSTGRES_PASSWORD", default="test_password"),
    "HOST":     config("POSTGRES_HOST",     default="localhost"),
    "PORT":     config("POSTGRES_PORT",     default="5432"),
}}

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

CELERY_TASK_ALWAYS_EAGER     = True
CELERY_TASK_EAGER_PROPAGATES = True
PSEUDONYMIZATION_SALT        = "test-salt-not-for-production"
MFA_ENCRYPTION_KEY           = "test-mfa-key-not-for-production"
PAYMENT_SHIELD_SECRET        = "test-payment-shield-secret"
COMMUNITY_NETWORK_KEY        = "test-network-key"
COMMUNITY_HUB_URL            = ""
COMMUNITY_NODE_API_KEY       = ""
COMMUNITY_SYNC_MINUTES       = 15

# Sin throttling global; los límites por endpoint (scope) se suben para que las
# pruebas no choquen entre sí. "mfa" se deja igual: test_mfa prueba su límite.
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": [],  # noqa
                  "DEFAULT_THROTTLE_RATES": {
                      **REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],  # noqa
                      "auth_login": "10000/min", "auth_refresh": "10000/min",
                      "auth_register": "10000/min", "auth_email": "10000/min",
                      "analyze": "10000/min",
                  }}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
AUTH_EMAIL_COOLDOWN_SECONDS = 0
