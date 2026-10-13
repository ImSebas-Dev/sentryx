from django.urls import path
from apps.threat_intel.views import IOCListCreateView, IOCCheckView, ThreatIntelStatsView

urlpatterns = [
    path("iocs/",   IOCListCreateView.as_view(), name="ioc_list_create"),
    path("check/",  IOCCheckView.as_view(),       name="ioc_check"),
    path("stats/",  ThreatIntelStatsView.as_view(),name="ti_stats"),
]
