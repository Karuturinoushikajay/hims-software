from __future__ import annotations

import base64
from io import BytesIO

import qrcode
from django.middleware.csrf import get_token
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Permission, Role, Screen, User
from apps.accounts.permissions import HasPermission, require_permission
from apps.accounts.serializers import (
    FacilitySwitchSerializer,
    LoginSerializer,
    PasswordChangeSerializer,
    RolePermissionsUpdateSerializer,
    RoleScreensUpdateSerializer,
    RoleSerializer,
    TotpConfirmSerializer,
    UserCreateSerializer,
    UserSerializer,
    UserUpdateSerializer,
)
from apps.accounts.services import (
    create_user,
    deactivate_user,
    login_user,
    logout_user,
    me_payload,
    set_role_permissions,
    set_role_screens,
    switch_facility,
    update_user,
)
from apps.audit.services import record_audit
from apps.common.exceptions import AppError


def _require_facility(request):
    if not getattr(request, "facility", None):
        raise AppError("No active facility. Switch facility first.", code="no_facility")
    return request.facility


class CsrfView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"csrfToken": get_token(request)})


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        ser = LoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        login_user(
            request,
            username=ser.validated_data["username"],
            password=ser.validated_data["password"],
            totp_token=ser.validated_data.get("totp_token") or None,
        )
        return Response(me_payload(request))


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout_user(request)
        return Response({"ok": True})


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(me_payload(request))


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = PasswordChangeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        if not request.user.check_password(ser.validated_data["current_password"]):
            raise AppError("Current password is incorrect.", code="bad_password")
        request.user.set_password(ser.validated_data["new_password"])
        request.user.save(update_fields=["password", "updated_at"])
        record_audit(
            action="auth.password_change",
            actor=request.user,
            facility=getattr(request, "facility", None),
            entity_type="User",
            entity_id=str(request.user.id),
            request=request,
        )
        return Response({"ok": True})


class TotpSetupView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        TOTPDevice.objects.filter(user=request.user, confirmed=False).delete()
        device = TOTPDevice.objects.create(user=request.user, name="default", confirmed=False)
        url = device.config_url
        img = qrcode.make(url)
        buf = BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return Response(
            {
                "otpauth_url": url,
                "qr_png_base64": b64,
                "device_id": device.id,
            }
        )


class TotpConfirmView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = TotpConfirmSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        device = TOTPDevice.objects.filter(user=request.user, confirmed=False).order_by("-id").first()
        if not device:
            raise AppError("No pending 2FA device. Call setup first.", code="no_device")
        if not device.verify_token(ser.validated_data["token"]):
            raise AppError("Invalid token.", code="totp_invalid")
        device.confirmed = True
        device.save(update_fields=["confirmed"])
        # Remove other unconfirmed; keep one confirmed set.
        request.user.totp_enabled = True
        request.user.save(update_fields=["totp_enabled", "updated_at"])
        request.session.pop("pending_2fa_setup", None)
        record_audit(
            action="auth.2fa_enabled",
            actor=request.user,
            facility=getattr(request, "facility", None),
            entity_type="User",
            entity_id=str(request.user.id),
            request=request,
        )
        return Response({"ok": True, "totp_enabled": True})


class FacilitySwitchView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = FacilitySwitchSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        facility = switch_facility(request, str(ser.validated_data["facility_id"]))
        return Response(
            {
                "active_facility_id": str(facility.id),
                "facility_code": facility.code,
                "facility_name": facility.name,
            }
        )


class UserListCreateView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    permission_code = "accounts.user.read"

    def get(self, request):
        facility = _require_facility(request)
        require_permission(request.user, facility, "accounts.user.read")
        users = (
            User.objects.filter(
                memberships__facility=facility,
                memberships__deleted_at__isnull=True,
            )
            .distinct()
            .prefetch_related("memberships__role", "memberships__facility")
            .order_by("username")
        )
        return Response(UserSerializer(users, many=True).data)

    def post(self, request):
        facility = _require_facility(request)
        ser = UserCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = create_user(actor=request.user, facility=facility, **ser.validated_data)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class UserDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, user_id):
        facility = _require_facility(request)
        user = User.objects.get(id=user_id)
        ser = UserUpdateSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        user = update_user(
            actor=request.user, facility=facility, user=user, data=ser.validated_data
        )
        return Response(UserSerializer(user).data)


class UserDeactivateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, user_id):
        facility = _require_facility(request)
        user = User.objects.get(id=user_id)
        user = deactivate_user(actor=request.user, facility=facility, user=user)
        return Response(UserSerializer(user).data)


class RoleListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _require_facility(request)
        require_permission(request.user, facility, "accounts.role.read")
        roles = Role.objects.filter(facility=facility).prefetch_related("permissions", "screens")
        return Response(RoleSerializer(roles, many=True).data)

    def post(self, request):
        facility = _require_facility(request)
        require_permission(request.user, facility, "accounts.role.create")
        code = request.data.get("code", "").upper().strip()
        name = request.data.get("name", "").strip()
        if not code or not name:
            raise AppError("code and name are required.", fields={"code": ["Required"], "name": ["Required"]})
        role = Role.objects.create(
            facility=facility,
            code=code,
            name=name,
            description=request.data.get("description", ""),
        )
        record_audit(
            action="accounts.role.create",
            actor=request.user,
            facility=facility,
            entity_type="Role",
            entity_id=str(role.id),
            after={"code": role.code, "name": role.name},
            request=request,
        )
        return Response(RoleSerializer(role).data, status=status.HTTP_201_CREATED)


class RolePermissionsView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, role_id):
        facility = _require_facility(request)
        role = Role.objects.get(id=role_id)
        ser = RolePermissionsUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        role = set_role_permissions(
            actor=request.user,
            facility=facility,
            role=role,
            permission_ids=ser.validated_data["permission_ids"],
        )
        role = Role.objects.prefetch_related("permissions", "screens").get(id=role.id)
        return Response(RoleSerializer(role).data)


class RoleScreensView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, role_id):
        facility = _require_facility(request)
        role = Role.objects.get(id=role_id)
        ser = RoleScreensUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        role = set_role_screens(
            actor=request.user,
            facility=facility,
            role=role,
            screen_ids=ser.validated_data["screen_ids"],
        )
        role = Role.objects.prefetch_related("permissions", "screens").get(id=role.id)
        return Response(RoleSerializer(role).data)


class PermissionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _require_facility(request)
        require_permission(request.user, facility, "accounts.role.read")
        return Response(
            [
                {"id": str(p.id), "code": p.code, "module": p.module, "action": p.action, "description": p.description}
                for p in Permission.objects.all()
            ]
        )


class ScreenListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _require_facility(request)
        require_permission(request.user, facility, "accounts.role.read")
        return Response(
            [
                {
                    "id": str(s.id),
                    "code": s.code,
                    "module": s.module,
                    "name": s.name,
                    "route": s.route,
                    "sort_order": s.sort_order,
                }
                for s in Screen.objects.filter(is_active=True)
            ]
        )
