from .base import *  # noqa

# Solo para tu máquina. Nunca uses este archivo en un servidor accesible desde
# Internet: el despliegue usa config.settings.production.
DEBUG = True

# No uses CORS_ALLOW_ALL_ORIGINS: junto con CORS_ALLOW_CREDENTIALS permite que
# cualquier página lea la API con la sesión del usuario. El frontend de
# desarrollo va por el proxy de Vite (mismo origen) y no necesita CORS.

# API navegable de DRF solo en desarrollo
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_RENDERER_CLASSES": [  # noqa
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
]}

LOGGING["root"]["level"] = "DEBUG"  # noqa
LOGGING["loggers"]["apps"]["level"] = "DEBUG"  # noqa
LOGGING["loggers"]["celery"] = {"handlers": ["console"], "level": "INFO", "propagate": False}  # noqa
