from django.contrib import admin

from apps.community.models import CommunityIndicator, CommunitySettings


@admin.register(CommunitySettings)
class CommunitySettingsAdmin(admin.ModelAdmin):
    list_display = ("organization", "enabled", "sector", "region", "node_status", "last_sync_at")
    # El consentimiento se da desde la interfaz: no lo edites a mano
    readonly_fields = ("consent_accepted_by", "consent_accepted_at", "consent_version")


@admin.register(CommunityIndicator)
class CommunityIndicatorAdmin(admin.ModelAdmin):
    list_display = ("ioc_hash", "ioc_type", "company_count", "last_seen")
