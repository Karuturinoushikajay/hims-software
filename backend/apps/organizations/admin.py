from django.contrib import admin

from apps.organizations.models import Facility, FacilitySettings, Organization


class FacilityInline(admin.TabularInline):
    model = Facility
    extra = 0


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "created_at")
    search_fields = ("code", "name")
    inlines = [FacilityInline]


class FacilitySettingsInline(admin.StackedInline):
    model = FacilitySettings
    can_delete = False


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "organization", "bed_capacity", "is_active")
    search_fields = ("code", "name")
    list_filter = ("organization", "is_active")
    inlines = [FacilitySettingsInline]


@admin.register(FacilitySettings)
class FacilitySettingsAdmin(admin.ModelAdmin):
    list_display = ("facility", "gstin", "tds_rate_confirmed", "session_timeout_minutes")
