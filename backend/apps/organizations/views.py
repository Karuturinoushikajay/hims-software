from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import require_permission
from apps.audit.services import record_audit
from apps.common.exceptions import AppError, ForbiddenError
from apps.organizations.models import Facility, FacilitySettings, Organization
from apps.organizations.serializers import (
    FacilitySerializer,
    FacilitySettingsSerializer,
    FacilitySettingsUpdateSerializer,
    OrganizationSerializer,
)


class OrganizationListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.is_superuser:
            # Facility admins see their org via facility membership
            org_ids = request.user.memberships.filter(
                is_active=True, deleted_at__isnull=True
            ).values_list("facility__organization_id", flat=True)
            qs = Organization.objects.filter(id__in=org_ids, deleted_at__isnull=True)
        else:
            qs = Organization.objects.filter(deleted_at__isnull=True)
        return Response(OrganizationSerializer(qs, many=True).data)

    def post(self, request):
        if not request.user.is_superuser:
            raise ForbiddenError("Only Super Admin can create organizations.")
        ser = OrganizationSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        org = Organization.objects.create(**ser.validated_data)
        record_audit(
            action="organizations.create",
            actor=request.user,
            entity_type="Organization",
            entity_id=str(org.id),
            after=OrganizationSerializer(org).data,
            request=request,
        )
        return Response(OrganizationSerializer(org).data, status=status.HTTP_201_CREATED)


class FacilityListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.is_superuser:
            qs = Facility.objects.filter(deleted_at__isnull=True).select_related(
                "organization", "settings"
            )
        else:
            facility_ids = request.user.memberships.filter(
                is_active=True, deleted_at__isnull=True
            ).values_list("facility_id", flat=True)
            qs = Facility.objects.filter(
                id__in=facility_ids, deleted_at__isnull=True
            ).select_related("organization", "settings")
        return Response(FacilitySerializer(qs, many=True).data)

    def post(self, request):
        if not request.user.is_superuser:
            raise ForbiddenError("Only Super Admin can create facilities.")
        data = request.data.copy()
        org_id = data.get("organization")
        if not org_id:
            raise AppError("organization is required.", fields={"organization": ["Required"]})
        org = Organization.objects.get(id=org_id)
        facility = Facility.objects.create(
            organization=org,
            name=data.get("name", ""),
            code=data.get("code", "").upper(),
            legal_name=data.get("legal_name", ""),
            address_line1=data.get("address_line1", ""),
            city=data.get("city", ""),
            state=data.get("state", ""),
            state_code=data.get("state_code", ""),
            pincode=data.get("pincode", ""),
            bed_capacity=int(data.get("bed_capacity") or 0),
        )
        FacilitySettings.objects.create(
            facility=facility,
            require_2fa_roles=["SUPER_ADMIN", "DOCTOR"],
        )
        record_audit(
            action="facilities.create",
            actor=request.user,
            facility=facility,
            entity_type="Facility",
            entity_id=str(facility.id),
            after=FacilitySerializer(facility).data,
            request=request,
        )
        return Response(FacilitySerializer(facility).data, status=status.HTTP_201_CREATED)


class FacilitySettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, facility_id):
        facility = Facility.objects.select_related("settings").get(id=facility_id)
        active = getattr(request, "facility", None)
        if not request.user.is_superuser:
            if not active or str(active.id) != str(facility.id):
                raise ForbiddenError("Cannot view another facility's settings.")
            require_permission(request.user, facility, "organizations.settings.read")
        return Response(FacilitySettingsSerializer(facility.settings).data)

    def patch(self, request, facility_id):
        facility = Facility.objects.select_related("settings").get(id=facility_id)
        active = getattr(request, "facility", None)
        if not request.user.is_superuser:
            if not active or str(active.id) != str(facility.id):
                raise ForbiddenError("Cannot update another facility's settings.")
            require_permission(request.user, facility, "organizations.settings.update")

        settings_obj = facility.settings
        before = FacilitySettingsSerializer(settings_obj).data
        ser = FacilitySettingsUpdateSerializer(settings_obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        record_audit(
            action="organizations.settings.update",
            actor=request.user,
            facility=facility,
            entity_type="FacilitySettings",
            entity_id=str(settings_obj.id),
            before=before,
            after=FacilitySettingsSerializer(settings_obj).data,
            request=request,
        )
        return Response(FacilitySettingsSerializer(settings_obj).data)
