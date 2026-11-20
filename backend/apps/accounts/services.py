from __future__ import annotations

from django.contrib.auth import authenticate, login, logout
from django.core.cache import cache
from django.db import transaction
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import Membership, Role, RolePermission, RoleScreen, User
from apps.accounts.permissions import user_has_permission, user_role_codes, user_screens
from apps.audit.services import record_audit
from apps.common.exceptions import AppError, ForbiddenError, ThrottledError, UnauthorizedError
from apps.organizations.models import Facility


def _client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _throttle_key(username: str, ip: str) -> str:
    return f"login_fail:{username.lower()}:{ip}"


def check_login_throttle(username: str, ip: str) -> None:
    from django.conf import settings

    key = _throttle_key(username, ip)
    fails = cache.get(key, 0)
    if fails >= settings.LOGIN_THROTTLE_LIMIT:
        raise ThrottledError(
            "Too many failed login attempts. Try again later.",
            code="login_throttled",
        )


def record_login_failure(username: str, ip: str) -> None:
    from django.conf import settings

    key = _throttle_key(username, ip)
    fails = cache.get(key, 0) + 1
    cache.set(key, fails, settings.LOGIN_THROTTLE_WINDOW_SECONDS)


def clear_login_failures(username: str, ip: str) -> None:
    cache.delete(_throttle_key(username, ip))


def roles_requiring_2fa(facility: Facility | None) -> list[str]:
    if not facility:
        return ["SUPER_ADMIN", "DOCTOR"]
    settings_obj = getattr(facility, "settings", None)
    if settings_obj and settings_obj.require_2fa_roles:
        return list(settings_obj.require_2fa_roles)
    return ["SUPER_ADMIN", "DOCTOR"]


def user_must_use_2fa(user: User, facility: Facility | None) -> bool:
    if user.totp_enabled:
        return True
    required = set(roles_requiring_2fa(facility))
    codes = set(user_role_codes(user, facility)) if facility else set()
    if user.is_superuser:
        codes.add("SUPER_ADMIN")
    return bool(codes & required)


def verify_totp(user: User, token: str) -> bool:
    devices = TOTPDevice.objects.filter(user=user, confirmed=True)
    return any(device.verify_token(token) for device in devices)


@transaction.atomic
def login_user(request, *, username: str, password: str, totp_token: str | None = None) -> User:
    ip = _client_ip(request)
    check_login_throttle(username, ip)

    user = authenticate(request, username=username.lower().strip(), password=password)
    if user is None:
        record_login_failure(username, ip)
        record_audit(
            action="auth.login_failed",
            actor=None,
            facility=None,
            entity_type="User",
            entity_id=username,
            after={"username": username, "ip": ip},
            request=request,
        )
        raise UnauthorizedError("Invalid username or password.", code="invalid_credentials")

    if not user.is_active or user.deleted_at:
        raise UnauthorizedError("Account is inactive.", code="inactive")

    # Pick a default facility for 2FA policy if none active yet.
    facility = getattr(request, "facility", None)
    if facility is None:
        membership = (
            user.memberships.filter(is_active=True, deleted_at__isnull=True)
            .select_related("facility", "facility__settings")
            .first()
        )
        if membership:
            facility = membership.facility

    needs_2fa = user_must_use_2fa(user, facility)
    has_device = TOTPDevice.objects.filter(user=user, confirmed=True).exists()

    if needs_2fa and not has_device:
        # Allow login but flag that setup is required; UI will force setup.
        request.session["pending_2fa_setup"] = True
    elif needs_2fa and has_device:
        if not totp_token:
            raise UnauthorizedError("Two-factor code required.", code="totp_required")
        if not verify_totp(user, totp_token):
            record_login_failure(username, ip)
            raise UnauthorizedError("Invalid two-factor code.", code="totp_invalid")
        request.session.pop("pending_2fa_setup", None)
    else:
        request.session.pop("pending_2fa_setup", None)

    login(request, user)
    clear_login_failures(username, ip)

    if facility and (
        user.is_superuser
        or user.memberships.filter(facility=facility, is_active=True, deleted_at__isnull=True).exists()
    ):
        request.session["active_facility_id"] = str(facility.id)
        request.facility = facility

    record_audit(
        action="auth.login",
        actor=user,
        facility=facility,
        entity_type="User",
        entity_id=str(user.id),
        after={"username": user.username},
        request=request,
    )
    return user


def logout_user(request) -> None:
    user = request.user if request.user.is_authenticated else None
    facility = getattr(request, "facility", None)
    record_audit(
        action="auth.logout",
        actor=user if user and user.is_authenticated else None,
        facility=facility,
        entity_type="User",
        entity_id=str(user.id) if user and user.is_authenticated else None,
        request=request,
    )
    logout(request)


@transaction.atomic
def create_user(
    *,
    actor: User,
    facility: Facility,
    username: str,
    password: str,
    first_name: str = "",
    last_name: str = "",
    email: str = "",
    phone: str = "",
    role_id: str | None = None,
) -> User:
    if not user_has_permission(actor, facility, "accounts.user.create"):
        raise ForbiddenError("Missing permission: accounts.user.create")

    if User.objects.filter(username=username.lower().strip()).exists():
        raise AppError("Username already exists.", code="username_taken", fields={"username": ["Taken"]})

    user = User.objects.create_user(
        username=username,
        password=password,
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
    )
    if role_id:
        role = Role.objects.get(id=role_id, facility=facility)
        Membership.objects.create(user=user, facility=facility, role=role)

    record_audit(
        action="accounts.user.create",
        actor=actor,
        facility=facility,
        entity_type="User",
        entity_id=str(user.id),
        after={
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role_id": str(role_id) if role_id else None,
        },
    )
    return user


@transaction.atomic
def update_user(*, actor: User, facility: Facility, user: User, data: dict) -> User:
    if not user_has_permission(actor, facility, "accounts.user.update"):
        raise ForbiddenError("Missing permission: accounts.user.update")

    before = {
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "phone": user.phone,
        "is_active": user.is_active,
    }
    for field in ("first_name", "last_name", "email", "phone", "is_active"):
        if field in data and data[field] is not None:
            setattr(user, field, data[field])
    user.save()
    record_audit(
        action="accounts.user.update",
        actor=actor,
        facility=facility,
        entity_type="User",
        entity_id=str(user.id),
        before=before,
        after={
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "phone": user.phone,
            "is_active": user.is_active,
        },
    )
    return user


@transaction.atomic
def deactivate_user(*, actor: User, facility: Facility, user: User) -> User:
    if not user_has_permission(actor, facility, "accounts.user.deactivate"):
        raise ForbiddenError("Missing permission: accounts.user.deactivate")
    before = {"is_active": user.is_active}
    user.is_active = False
    user.save(update_fields=["is_active", "updated_at"])
    user.memberships.filter(facility=facility).update(is_active=False)
    record_audit(
        action="accounts.user.deactivate",
        actor=actor,
        facility=facility,
        entity_type="User",
        entity_id=str(user.id),
        before=before,
        after={"is_active": False},
    )
    return user


@transaction.atomic
def set_role_permissions(*, actor: User, facility: Facility, role: Role, permission_ids: list) -> Role:
    if not user_has_permission(actor, facility, "accounts.role.update"):
        raise ForbiddenError("Missing permission: accounts.role.update")
    if role.facility_id != facility.id:
        raise ForbiddenError("Role does not belong to this facility.")

    before = list(role.permissions.values_list("code", flat=True))
    RolePermission.objects.filter(role=role).delete()
    from apps.accounts.models import Permission

    perms = Permission.objects.filter(id__in=permission_ids)
    RolePermission.objects.bulk_create(
        [RolePermission(role=role, permission=p) for p in perms]
    )
    after = list(role.permissions.values_list("code", flat=True))
    record_audit(
        action="accounts.role.permissions",
        actor=actor,
        facility=facility,
        entity_type="Role",
        entity_id=str(role.id),
        before={"permissions": before},
        after={"permissions": after},
    )
    return role


@transaction.atomic
def set_role_screens(*, actor: User, facility: Facility, role: Role, screen_ids: list) -> Role:
    if not user_has_permission(actor, facility, "accounts.role.update"):
        raise ForbiddenError("Missing permission: accounts.role.update")
    if role.facility_id != facility.id:
        raise ForbiddenError("Role does not belong to this facility.")

    before = list(role.screens.values_list("code", flat=True))
    RoleScreen.objects.filter(role=role).delete()
    from apps.accounts.models import Screen

    screens = Screen.objects.filter(id__in=screen_ids)
    RoleScreen.objects.bulk_create(
        [
            RoleScreen(role=role, screen=s, sort_order=i)
            for i, s in enumerate(screens)
        ]
    )
    after = list(role.screens.values_list("code", flat=True))
    record_audit(
        action="accounts.role.screens",
        actor=actor,
        facility=facility,
        entity_type="Role",
        entity_id=str(role.id),
        before={"screens": before},
        after={"screens": after},
    )
    return role


def switch_facility(request, facility_id: str) -> Facility:
    user = request.user
    facility = Facility.objects.select_related("settings").get(
        id=facility_id, is_active=True, deleted_at__isnull=True
    )
    if not user.is_superuser and not user.memberships.filter(
        facility=facility, is_active=True, deleted_at__isnull=True
    ).exists():
        raise ForbiddenError("No membership at this facility.")
    request.session["active_facility_id"] = str(facility.id)
    request.facility = facility
    record_audit(
        action="session.facility_switch",
        actor=user,
        facility=facility,
        entity_type="Facility",
        entity_id=str(facility.id),
        request=request,
    )
    return facility


def me_payload(request) -> dict:
    user = request.user
    facility = getattr(request, "facility", None)
    memberships = (
        user.memberships.filter(is_active=True, deleted_at__isnull=True)
        .select_related("facility", "role")
        .all()
    )
    screens = list(user_screens(user, facility).values("id", "code", "module", "name", "route"))
    return {
        "id": str(user.id),
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "phone": user.phone,
        "totp_enabled": user.totp_enabled,
        "pending_2fa_setup": bool(request.session.get("pending_2fa_setup")),
        "is_superuser": user.is_superuser,
        "active_facility_id": str(facility.id) if facility else None,
        "roles": user_role_codes(user, facility) if facility else [],
        "screens": screens,
        "memberships": [
            {
                "facility_id": str(m.facility_id),
                "facility_code": m.facility.code,
                "facility_name": m.facility.name,
                "role_code": m.role.code,
                "role_name": m.role.name,
            }
            for m in memberships
        ],
    }
