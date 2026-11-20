from __future__ import annotations

from rest_framework.permissions import BasePermission

from apps.common.exceptions import ForbiddenError


def user_has_permission(user, facility, permission_code: str) -> bool:
    if not user or not user.is_authenticated or not facility:
        return False
    if user.is_superuser:
        return True
    return (
        user.memberships.filter(
            facility=facility,
            is_active=True,
            deleted_at__isnull=True,
            role__permissions__code=permission_code,
        )
        .exists()
    )


def require_permission(user, facility, permission_code: str) -> None:
    if not user_has_permission(user, facility, permission_code):
        raise ForbiddenError(
            f"Missing permission: {permission_code}",
            code="permission_denied",
        )


def user_role_codes(user, facility) -> list[str]:
    if not user or not facility:
        return []
    return list(
        user.memberships.filter(
            facility=facility,
            is_active=True,
            deleted_at__isnull=True,
        ).values_list("role__code", flat=True)
    )


def user_screens(user, facility):
    from apps.accounts.models import Screen

    if not user or not facility:
        return Screen.objects.none()
    if user.is_superuser:
        return Screen.objects.filter(is_active=True)
    role_ids = user.memberships.filter(
        facility=facility,
        is_active=True,
        deleted_at__isnull=True,
    ).values_list("role_id", flat=True)
    return (
        Screen.objects.filter(is_active=True, rolescreen__role_id__in=role_ids)
        .distinct()
        .order_by("sort_order", "module", "name")
    )



class HasPermission(BasePermission):
    permission_code: str = ""

    def has_permission(self, request, view) -> bool:
        code = getattr(view, "permission_code", None) or self.permission_code
        if not code:
            return True
        facility = getattr(request, "facility", None)
        return user_has_permission(request.user, facility, code)
