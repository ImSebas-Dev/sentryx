"""Sentryx v2 — URLs de la Red de alerta."""
from django.urls import path

from apps.community import views

urlpatterns = [
    path("settings/", views.SettingsView.as_view(), name="community_settings"),
    path("enable/",   views.EnableView.as_view(),   name="community_enable"),
    path("disable/",  views.DisableView.as_view(),  name="community_disable"),
    path("sync/",     views.SyncNowView.as_view(),  name="community_sync"),
    path("summary/",  views.SummaryView.as_view(),  name="community_summary"),
]
