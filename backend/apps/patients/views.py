from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import require_permission
from apps.audit.services import record_audit
from apps.common.exceptions import AppError
from apps.patients.models import Patient, Registration
from apps.patients.serializers import RegisterSerializer
from apps.patients.services import patient_payload, register_patient, search_patients


def _facility(request):
    facility = getattr(request, "facility", None)
    if not facility:
        raise AppError("No active facility.", code="no_facility")
    return facility


class PatientSearchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "patients.read")
        query = request.query_params.get("q", "")
        rows = search_patients(facility.organization, query)
        record_audit(
            action="patients.search",
            actor=request.user,
            facility=facility,
            entity_type="Patient",
            after={"q": query, "count": rows.count()},
            request=request,
        )
        return Response([patient_payload(p) for p in rows])


class PatientRecentView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "patients.read")
        regs = (
            Registration.objects.filter(facility=facility)
            .select_related("patient")
            .order_by("-created_at")[:8]
        )
        return Response([patient_payload(r.patient, r) for r in regs])


class PatientDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, patient_id):
        facility = _facility(request)
        require_permission(request.user, facility, "patients.read")
        patient = Patient.objects.get(id=patient_id, organization=facility.organization)
        registration = patient.registrations.filter(facility=facility).order_by("-created_at").first()
        record_audit(
            action="patients.view",
            actor=request.user,
            facility=facility,
            entity_type="Patient",
            entity_id=str(patient.id),
            request=request,
        )
        return Response(patient_payload(patient, registration))


class RegisterView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        facility = _facility(request)
        ser = RegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        payload = dict(ser.validated_data)
        if payload.get("date_of_birth"):
            payload["date_of_birth"] = payload["date_of_birth"]
        result = register_patient(
            actor=request.user,
            facility=facility,
            data=payload,
            idempotency_key=request.headers.get("Idempotency-Key", ""),
        )
        return Response(result, status=201)
