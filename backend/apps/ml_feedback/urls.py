from django.urls import path
from apps.ml_feedback.views import (
    RetrainTriggerView, RetrainStatusView,
    RetrainHistoryView, FeedbackStatsView, FeedbackCreateView,
)

urlpatterns = [
    path("retrain/",         RetrainTriggerView.as_view(),  name="retrain_trigger"),
    path("retrain/status/",  RetrainStatusView.as_view(),   name="retrain_status"),
    path("retrain/history/", RetrainHistoryView.as_view(),  name="retrain_history"),
    path("feedback/stats/",  FeedbackStatsView.as_view(),   name="feedback_stats"),
    path("feedback/",        FeedbackCreateView.as_view(),  name="feedback_create"),
]
