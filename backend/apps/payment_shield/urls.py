"""Sentryx v2 — URLs del Escudo de pagos."""
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from apps.payment_shield.views import (
    PaymentCheckDetailView, PaymentCheckListView, PaymentCheckVerifyView,
    PaymentRiskAcknowledgeView, SupplierViewSet,
)

router = SimpleRouter()
router.register("suppliers", SupplierViewSet, basename="supplier")

urlpatterns = [
    path("", include(router.urls)),
    path("checks/",                  PaymentCheckListView.as_view(),   name="payment_check_list"),
    path("checks/<uuid:pk>/",        PaymentCheckDetailView.as_view(), name="payment_check_detail"),
    path("checks/<uuid:pk>/verify/", PaymentCheckVerifyView.as_view(), name="payment_check_verify"),
    path("checks/<uuid:pk>/acknowledge-risk/", PaymentRiskAcknowledgeView.as_view(),
         name="payment_check_ack"),
]
