from django.contrib import admin

from apps.payment_shield.models import PaymentCheck, Supplier


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display  = ("name", "organization", "nit", "dv", "bank_name", "account_last4")
    list_filter   = ("organization",)
    search_fields = ("name", "nit")
    # No permitas editar el HMAC a mano: se calcula solo desde la API.
    readonly_fields = ("account_hmac", "account_last4")


@admin.register(PaymentCheck)
class PaymentCheckAdmin(admin.ModelAdmin):
    list_display = ("id", "organization", "verdict", "status", "sender_domain", "created_at")
    list_filter  = ("verdict", "status")
