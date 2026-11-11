import os
from django.core.wsgi import get_wsgi_application

# Por defecto producción: si alguien olvida DJANGO_SETTINGS_MODULE en un
# servidor, mejor que falle por un secreto faltante que arrancar con DEBUG=True.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
application = get_wsgi_application()
