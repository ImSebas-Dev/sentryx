from django.urls import path
from apps.incidents.views import IncidentListCreateView, IncidentDetailView

urlpatterns = [
    path("",           IncidentListCreateView.as_view(), name="incident_list_create"),
    path("<uuid:pk>/", IncidentDetailView.as_view(),     name="incident_detail"),
]
