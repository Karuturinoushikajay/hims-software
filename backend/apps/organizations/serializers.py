from rest_framework import serializers

from apps.organizations.models import Facility, FacilitySettings, Organization


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ("id", "name", "code", "is_active", "created_at")


class FacilitySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = FacilitySettings
        fields = (
            "id",
            "gstin",
            "gstin_confirmed",
            "financial_year_start_month",
            "financial_year_start_day",
            "session_timeout_minutes",
            "refund_auth_threshold",
            "tds_commission_rate",
            "tds_rate_confirmed",
            "require_2fa_roles",
            "logo",
            "letterhead_text",
        )


class FacilitySerializer(serializers.ModelSerializer):
    settings = FacilitySettingsSerializer(read_only=True)
    organization_code = serializers.CharField(source="organization.code", read_only=True)

    class Meta:
        model = Facility
        fields = (
            "id",
            "organization",
            "organization_code",
            "name",
            "code",
            "legal_name",
            "address_line1",
            "address_line2",
            "city",
            "state",
            "state_code",
            "pincode",
            "country",
            "phone",
            "email",
            "bed_capacity",
            "timezone",
            "currency",
            "is_active",
            "settings",
            "created_at",
        )


class FacilitySettingsUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = FacilitySettings
        fields = (
            "gstin",
            "gstin_confirmed",
            "financial_year_start_month",
            "financial_year_start_day",
            "session_timeout_minutes",
            "refund_auth_threshold",
            "tds_commission_rate",
            "tds_rate_confirmed",
            "require_2fa_roles",
            "logo",
            "letterhead_text",
        )
