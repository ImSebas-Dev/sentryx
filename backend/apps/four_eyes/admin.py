from django.contrib import admin

from apps.four_eyes.models import ApprovalRequest, FourEyesPolicy


@admin.register(FourEyesPolicy)
class FourEyesPolicyAdmin(admin.ModelAdmin):
    list_display = ("organization", "enabled", "min_severity", "expiry_minutes")


@admin.register(ApprovalRequest)
class ApprovalRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "organization", "status", "requester", "decided_by", "created_at")
    list_filter  = ("status",)
    # Deja las decisiones de solo lectura: se toman en la API, donde están las
    # reglas de separación de funciones y el código TOTP.
    readonly_fields = ("status", "decided_by", "decided_at", "decision_note")
