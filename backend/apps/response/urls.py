"""Sentryx v2 — URLs de la respuesta guiada."""
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from apps.response import views

router = SimpleRouter()
router.register("contacts", views.EmergencyContactViewSet, basename="emergency-contact")

urlpatterns = [
    path("", include(router.urls)),
    path("playbooks/", views.PlaybookListView.as_view(), name="response_playbooks"),
    path("config/",    views.ResponseConfigView.as_view(), name="response_config"),
    path("start/",     views.StartSessionView.as_view(), name="response_start"),
    path("<uuid:pk>/", views.SessionDetailView.as_view(), name="response_session"),
    path("<uuid:pk>/steps/<slug:step_id>/", views.StepView.as_view(), name="response_step"),
    path("<uuid:pk>/complete/", views.CompleteView.as_view(), name="response_complete"),
    path("<uuid:pk>/report.pdf", views.ReportView.as_view(), name="response_report"),
]
