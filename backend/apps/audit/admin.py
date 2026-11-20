from django.contrib import admin

from apps.audit.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "actor", "facility", "entity_type", "entity_id")
    list_filter = ("action",)
    search_fields = ("action", "entity_id", "request_id")
    readonly_fields = (
        "id",
        "created_at",
        "actor",
        "facility",
        "action",
        "entity_type",
        "entity_id",
        "before",
        "after",
        "ip_address",
        "user_agent",
        "request_id",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
