from django.contrib import admin

from apps.response.models import EmergencyContact, Playbook, ResponseSession


@admin.register(Playbook)
class PlaybookAdmin(admin.ModelAdmin):
    list_display = ("key", "title", "severity", "is_active")


@admin.register(EmergencyContact)
class EmergencyContactAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "kind", "phone")
    list_filter  = ("kind", "organization")


@admin.register(ResponseSession)
class ResponseSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "organization", "playbook", "status", "started_at")
    list_filter  = ("status",)
