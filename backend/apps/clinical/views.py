from __future__ import annotations

from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import require_permission
from apps.clinical import services
from apps.clinical.models import ClinicalNote, Prescription
from apps.clinical.pdfs import render_clinical_summary_pdf, render_prescription_pdf
from apps.common.exceptions import AppError
from apps.opd.models import Visit


def _facility(request):
    facility = getattr(request, "facility", None)
    if not facility:
        raise AppError("No active facility.", code="no_facility")
    return facility


class CatalogView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "clinical.read")
        q = request.query_params.get("q", "")
        return Response(
            {
                "drugs": services.list_drugs(facility),
                "icd": services.search_icd(q),
                "templates": services.list_prescription_templates(facility),
            }
        )


class TimelineView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, patient_id):
        facility = _facility(request)
        require_permission(request.user, facility, "clinical.read")
        return Response(services.patient_timeline(facility, patient_id))


class VisitNoteView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, visit_id):
        facility = _facility(request)
        require_permission(request.user, facility, "clinical.read")
        visit = Visit.objects.filter(id=visit_id, facility=facility).select_related("clinical_note").first()
        if not visit:
            raise AppError("Visit not found in this facility.", code="not_found")
        try:
            note = visit.clinical_note
        except ClinicalNote.DoesNotExist:
            return Response(
                {
                    "id": "",
                    "visit_id": str(visit.id),
                    "visit_no": visit.visit_no,
                    "patient_id": str(visit.patient_id),
                    "doctor": visit.doctor.name,
                    "complaints": "",
                    "history": "",
                    "examination": "",
                    "advice": "",
                    "diagnoses": [
                        {
                            "name": d.name,
                            "icd_code": d.icd_code.code if d.icd_code_id else "",
                            "is_primary": d.is_primary,
                        }
                        for d in visit.diagnoses.select_related("icd_code")
                    ],
                }
            )
        return Response(services.note_payload(note))

    def put(self, request, visit_id):
        facility = _facility(request)
        note = services.save_clinical_note(
            actor=request.user,
            facility=facility,
            visit_id=visit_id,
            data=request.data,
            request=request,
        )
        return Response(services.note_payload(note))


class AllergyView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "clinical.read")
        patient_id = request.query_params.get("patient_id")
        if not patient_id:
            raise AppError("patient_id is required.", code="invalid")
        return Response(services.list_allergies(facility, patient_id))

    def post(self, request):
        facility = _facility(request)
        row = services.record_allergy(
            actor=request.user, facility=facility, data=request.data, request=request
        )
        return Response(
            {
                "id": str(row.id),
                "substance": row.substance,
                "severity": row.severity,
                "reaction": row.reaction,
            },
            status=201,
        )


class PrescriptionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        facility = _facility(request)
        rx = services.issue_prescription(
            actor=request.user, facility=facility, data=request.data, request=request
        )
        return Response(services.prescription_payload(rx), status=201)


class PrescriptionPdfView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, prescription_id):
        facility = _facility(request)
        require_permission(request.user, facility, "clinical.read")
        try:
            rx = Prescription.objects.select_related("visit__patient", "doctor", "facility").get(
                id=prescription_id, facility=facility
            )
        except Prescription.DoesNotExist as exc:
            raise AppError("Prescription not found.", code="not_found") from exc
        pdf = render_prescription_pdf(rx)
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="rx-{rx.id}.pdf"'
        return response


class SummaryPdfView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, visit_id):
        facility = _facility(request)
        require_permission(request.user, facility, "clinical.read")
        try:
            note = ClinicalNote.objects.select_related("visit__patient", "doctor", "facility").get(
                visit_id=visit_id, facility=facility
            )
        except ClinicalNote.DoesNotExist as exc:
            raise AppError("Save a clinical note before printing the summary.", code="not_found") from exc
        pdf = render_clinical_summary_pdf(note)
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="summary-{visit_id}.pdf"'
        return response


class OrderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        facility = _facility(request)
        row = services.place_order(
            actor=request.user, facility=facility, data=request.data, request=request
        )
        return Response(
            {
                "id": str(row.id),
                "kind": row.kind,
                "name": row.name,
                "status": row.status,
                "code": row.code,
            },
            status=201,
        )


class FollowUpView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        facility = _facility(request)
        row = services.schedule_follow_up(
            actor=request.user, facility=facility, data=request.data, request=request
        )
        return Response(
            {
                "id": str(row.id),
                "follow_up_on": row.follow_up_on.isoformat(),
                "reason": row.reason,
                "visit_id": str(row.visit_id),
            },
            status=201,
        )


class AttachmentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        facility = _facility(request)
        uploaded = request.FILES.get("file")
        row = services.add_attachment(
            actor=request.user,
            facility=facility,
            patient_id=request.data.get("patient_id"),
            visit_id=request.data.get("visit_id") or None,
            uploaded_file=uploaded,
            description=request.data.get("description") or "",
            request=request,
        )
        return Response(
            {
                "id": str(row.id),
                "description": row.description,
                "url": row.file.url,
                "content_type": row.content_type,
            },
            status=201,
        )
