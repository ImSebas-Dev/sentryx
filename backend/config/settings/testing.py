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

REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": []}  # noqa
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
