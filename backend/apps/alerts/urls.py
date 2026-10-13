"""Sentryx v2 — URLs del módulo de alertas."""
from django.urls import path
from apps.alerts.views import (
    AlertListView, AlertDetailView, EmailAnalyzeView,
    AlertStatsView, CampaignListView,
)
from apps.alerts.report_views import (
    ReportDownloadView, ReportOptionsView, ReportPreviewView,
)

urlpatterns = [
    # Análisis de correos (endpoint principal)
    path("analyze/",          EmailAnalyzeView.as_view(),   name="email_analyze"),

    # Alertas
    path("",                  AlertListView.as_view(),      name="alert_list"),
    path("<uuid:pk>/",        AlertDetailView.as_view(),    name="alert_detail"),

    # Estadísticas del dashboard
    path("stats/",            AlertStatsView.as_view(),     name="alert_stats"),

    # Campañas
    path("campaigns/",        CampaignListView.as_view(),   name="campaign_list"),

    # Informes semanales y mensuales
    path("report/",           ReportDownloadView.as_view(), name="report_download"),
    path("report/preview/",   ReportPreviewView.as_view(),  name="report_preview"),
    path("report/options/",   ReportOptionsView.as_view(),  name="report_options"),
]
