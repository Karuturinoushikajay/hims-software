from __future__ import annotations

from django.utils.dateparse import parse_date
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import require_permission
from apps.common.exceptions import AppError
from apps.masters.models import PRO, Area, Doctor, OrganizationParty, Procedure, ReferralDoctor
from apps.opd.models import Appointment
from apps.opd.serializers import AppointmentSerializer, ConsultationSerializer, ProcedureSerializer
from apps.opd.services import (
    appointment_payload,
    book_appointment,
    create_consultation,
    create_procedure_order,
)
from apps.patients.models import Patient


def _facility(request):
    facility = getattr(request, "facility", None)
    if not facility:
        raise AppError("No active facility.", code="no_facility")
    return facility


class LookupView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "patients.read")
        doctors = Doctor.objects.filter(facility=facility, is_active=True).select_related(
            "department", "specialization"
        )
        return Response(
            {
                "registration_fee": str(facility.settings.registration_fee),
                "registration_validity_days": facility.settings.registration_validity_days,
                "doctors": [
                    {
                        "id": str(d.id),
                        "name": d.name,
                        "department": d.department.name,
                        "specialization": d.specialization.name,
                        "consultation_fee": str(d.consultation_fee),
                        "review_days": d.review_days,
                    }
                    for d in doctors
                ],
                "referrals": [
                    {"id": str(r.id), "name": r.name}
                    for r in ReferralDoctor.objects.filter(facility=facility, is_active=True)
                ],
                "pros": [
                    {"id": str(p.id), "name": p.name}
                    for p in PRO.objects.filter(facility=facility, is_active=True)
                ],
                "parties": [
                    {"id": str(p.id), "name": p.name, "kind": p.kind}
                    for p in OrganizationParty.objects.filter(facility=facility, is_active=True)
                ],
                "procedures": [
                    {"id": str(p.id), "name": p.name, "amount": str(p.amount)}
                    for p in Procedure.objects.filter(facility=facility, is_active=True)
                ],
                "areas": [
                    {"state": a.state, "city": a.city, "name": a.name}
                    for a in Area.objects.all()[:50]
                ],
            }
        )


class AppointmentView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "opd.appointment.manage")
        qs = Appointment.objects.filter(facility=facility).select_related("patient", "doctor")
        if request.query_params.get("doctor"):
            qs = qs.filter(doctor_id=request.query_params["doctor"])
        if request.query_params.get("date"):
            qs = qs.filter(service_date=parse_date(request.query_params["date"]))
        return Response([appointment_payload(row) for row in qs.order_by("token")[:100]])

    def post(self, request):
        facility = _facility(request)
        ser = AppointmentSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        patient = Patient.objects.get(
            id=ser.validated_data["patient_id"], organization=facility.organization
        )
        doctor = Doctor.objects.get(id=ser.validated_data["doctor_id"], facility=facility)
        row = book_appointment(
            actor=request.user,
            facility=facility,
            patient=patient,
            doctor=doctor,
            source=ser.validated_data["source"],
        )
        return Response(appointment_payload(row), status=201)


class ConsultationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        facility = _facility(request)
        ser = ConsultationSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        result = create_consultation(
            actor=request.user,
            facility=facility,
            data=ser.validated_data,
            idempotency_key=request.headers.get("Idempotency-Key", ""),
        )
        return Response(result, status=201)


class ProcedureOrderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        facility = _facility(request)
        ser = ProcedureSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        result = create_procedure_order(
            actor=request.user,
            facility=facility,
            data=ser.validated_data,
            idempotency_key=request.headers.get("Idempotency-Key", ""),
        )
        return Response(result, status=201)
