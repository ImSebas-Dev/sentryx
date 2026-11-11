from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.users.models import ShieldUser


@admin.register(ShieldUser)
class ShieldUserAdmin(UserAdmin):
    """
    Aquí se agrega a una persona a su empresa, se le cambia el rol o se desactiva
    su cuenta. No agregues los campos mfa_* ni los tokens: son secretos.
    """
    list_display  = ("email", "organization", "role", "is_email_verified", "is_active", "created_at")
    list_filter   = ("role", "is_active", "is_email_verified")
    search_fields = ("email", "username", "organization")
    ordering      = ("-created_at",)
    readonly_fields = ("is_email_verified", "created_at", "last_login", "date_joined")
    fieldsets = (
        (None, {"fields": ("email", "username", "password")}),
        ("Empresa y rol", {"fields": ("organization", "role")}),
        ("Estado", {"fields": ("is_active", "is_email_verified", "created_at", "last_login", "date_joined")}),
        ("Acceso a este panel", {"fields": ("is_staff", "is_superuser")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",),
                "fields": ("email", "username", "organization", "role", "password1", "password2")}),
    )
