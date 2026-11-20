from rest_framework import serializers

from apps.accounts.models import Membership, Permission, Role, Screen, User


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
    totp_token = serializers.CharField(required=False, allow_blank=True)


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField()
    new_password = serializers.CharField(min_length=8)


class TotpConfirmSerializer(serializers.Serializer):
    token = serializers.CharField(min_length=6, max_length=8)


class FacilitySwitchSerializer(serializers.Serializer):
    facility_id = serializers.UUIDField()


class UserCreateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=64)
    password = serializers.CharField(min_length=8, write_only=True)
    first_name = serializers.CharField(required=False, allow_blank=True, default="")
    last_name = serializers.CharField(required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    phone = serializers.CharField(required=False, allow_blank=True, default="")
    role_id = serializers.UUIDField(required=False, allow_null=True)


class UserUpdateSerializer(serializers.Serializer):
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)


class MembershipSerializer(serializers.ModelSerializer):
    role_code = serializers.CharField(source="role.code", read_only=True)
    role_name = serializers.CharField(source="role.name", read_only=True)
    facility_code = serializers.CharField(source="facility.code", read_only=True)

    class Meta:
        model = Membership
        fields = (
            "id",
            "facility",
            "facility_code",
            "role",
            "role_code",
            "role_name",
            "is_active",
        )


class UserSerializer(serializers.ModelSerializer):
    memberships = MembershipSerializer(many=True, read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "phone",
            "is_active",
            "totp_enabled",
            "memberships",
            "created_at",
        )


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ("id", "code", "module", "action", "description")


class ScreenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Screen
        fields = ("id", "code", "module", "name", "route", "sort_order")


class RoleSerializer(serializers.ModelSerializer):
    permissions = PermissionSerializer(many=True, read_only=True)
    screens = ScreenSerializer(many=True, read_only=True)

    class Meta:
        model = Role
        fields = (
            "id",
            "code",
            "name",
            "description",
            "is_system",
            "max_discount_percent",
            "max_discount_amount",
            "own_collection_only",
            "permissions",
            "screens",
        )


class RolePermissionsUpdateSerializer(serializers.Serializer):
    permission_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=True)


class RoleScreensUpdateSerializer(serializers.Serializer):
    screen_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=True)
