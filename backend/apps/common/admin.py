from django.contrib import admin

from apps.common.models import IdempotencyKey


@admin.register(IdempotencyKey)
class IdempotencyKeyAdmin(admin.ModelAdmin):
    list_display = ("key", "facility", "method", "path", "response_status", "created_at")
    search_fields = ("key", "path")
    readonly_fields = ("id", "created_at", "updated_at")
