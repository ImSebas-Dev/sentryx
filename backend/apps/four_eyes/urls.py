"""Sentryx v2 — URLs del control de cuatro ojos."""
from django.urls import path

from apps.four_eyes import views

urlpatterns = [
    path("policy/",                   views.PolicyView.as_view(),            name="four_eyes_policy"),
    path("stats/",                    views.FourEyesStatsView.as_view(),     name="four_eyes_stats"),
    path("requests/",                 views.RequestListCreateView.as_view(), name="four_eyes_requests"),
    path("requests/<uuid:pk>/",       views.RequestDetailView.as_view(),     name="four_eyes_request"),
    path("requests/<uuid:pk>/approve/", views.RequestApproveView.as_view(),  name="four_eyes_approve"),
    path("requests/<uuid:pk>/reject/",  views.RequestRejectView.as_view(),   name="four_eyes_reject"),
    path("requests/<uuid:pk>/cancel/",  views.RequestCancelView.as_view(),   name="four_eyes_cancel"),
    path("requests/<uuid:pk>/status/",  views.RequestStatusView.as_view(),   name="four_eyes_status"),
]
