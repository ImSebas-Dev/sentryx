"""Sentryx v2 — URL dispatcher."""
from django.conf import settings
from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.users.admin_auth import MFAAdminAuthenticationForm


def health_check(request):
    return JsonResponse({"status": "ok", "service": "sentryx-backend"})


# El login del panel pide también el código 2FA (apps/users/admin_auth.py)
admin.site.login_form = MFAAdminAuthenticationForm
admin.site.site_header = "Sentryx — Administración"

urlpatterns = [
    path("api/v1/health/",       health_check),
    path("api/v1/auth/",         include("apps.users.urls")),
    path("api/v1/alerts/",       include("apps.alerts.urls")),
    path("api/v1/incidents/",    include("apps.incidents.urls")),
    path("api/v1/threat-intel/", include("apps.threat_intel.urls")),
    path("api/v1/audit/",        include("apps.audit.urls")),
    path("api/v1/ml/",           include("apps.ml_feedback.urls")),
    path("api/v1/payment-shield/", include("apps.payment_shield.urls")),
    path("api/v1/four-eyes/",    include("apps.four_eyes.urls")),
    path("api/v1/response/",     include("apps.response.urls")),
    path("api/v1/community/",    include("apps.community.urls")),
    # OpenAPI: permisos según SPECTACULAR_SETTINGS["SERVE_PERMISSIONS"]
    path("api/v1/schema/",       SpectacularAPIView.as_view(), name="schema"),
    path("api/v1/docs/",         SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]

if settings.ADMIN_ENABLED:
    urlpatterns.append(path(settings.ADMIN_URL, admin.site.urls))
