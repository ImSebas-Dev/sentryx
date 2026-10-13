"""Sentryx v2 — URL dispatcher."""
from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


def health_check(request):
    return JsonResponse({"status": "ok", "service": "sentryx-backend", "version": "2.0"})


urlpatterns = [
    path("api/v1/health/",       health_check),
    path("admin/",               admin.site.urls),
    path("api/v1/auth/",         include("apps.users.urls")),
    path("api/v1/alerts/",       include("apps.alerts.urls")),
    path("api/v1/incidents/",    include("apps.incidents.urls")),
    path("api/v1/threat-intel/", include("apps.threat_intel.urls")),
    path("api/v1/audit/",        include("apps.audit.urls")),
    path("api/v1/ml/",           include("apps.ml_feedback.urls")),
    # OpenAPI: permisos según SPECTACULAR_SETTINGS["SERVE_PERMISSIONS"]
    path("api/v1/schema/",       SpectacularAPIView.as_view(), name="schema"),
    path("api/v1/docs/",         SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]
