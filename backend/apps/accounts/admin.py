from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.accounts.models import (
    Membership,
    Permission,
    Role,
    RolePermission,
    RoleScreen,
    Screen,
    User,
)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("username",)
    list_display = ("username", "email", "first_name", "last_name", "is_active", "totp_enabled")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal", {"fields": ("first_name", "last_name", "email", "phone")}),
        ("Flags", {"fields": ("is_active", "is_staff", "is_superuser", "totp_enabled", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "password1", "password2", "is_staff", "is_superuser"),
            },
        ),
    )
    search_fields = ("username", "email", "first_name", "last_name")


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("code", "module", "action")
    search_fields = ("code",)


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "facility", "is_system")
    list_filter = ("facility",)


@admin.register(Screen)
class ScreenAdmin(admin.ModelAdmin):
    list_display = ("code", "module", "name", "route", "sort_order")


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "facility", "role", "is_active")


admin.site.register(RolePermission)
admin.site.register(RoleScreen)
