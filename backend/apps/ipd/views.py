from __future__ import annotations

from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import require_permission
from apps.common.exceptions import AppError
from apps.ipd import pdfs, services
from apps.ipd.models import CertificateKind


def _facility(request):
    facility = getattr(request, "facility", None)
    if not facility:
        raise AppError("No active facility.", code="no_facility")
    return facility


class BedBoardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "ipd.read")
        return Response(services.bed_board(facility))


class AdmissionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "ipd.read")
        return Response(
            services.list_admissions(
                facility,
                status=request.query_params.get("status") or "",
                q=request.query_params.get("q") or "",
            )
        )

    def post(self, request):
        facility = _facility(request)
        return Response(
            services.admit(actor=request.user, facility=facility, data=request.data, request=request),
            status=201,
        )


class AdmissionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, admission_id):
        facility = _facility(request)
        require_permission(request.user, facility, "ipd.read")
        return Response(services.get_admission(facility, admission_id))


class TransferDoctorView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, admission_id):
        facility = _facility(request)
        return Response(
            services.transfer_doctor(
                actor=request.user,
                facility=facility,
                admission_id=admission_id,
                data=request.data,
                request=request,
            )
        )


class TransferBedView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, admission_id):
        facility = _facility(request)
        return Response(
            services.transfer_bed(
                actor=request.user,
                facility=facility,
                admission_id=admission_id,
                data=request.data,
                request=request,
            )
        )


class DailyChargeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        facility = _facility(request)
        return Response(
            services.post_daily_charges(
                actor=request.user, facility=facility, data=request.data, request=request
            )
        )


class NursingNoteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, admission_id):
        facility = _facility(request)
        return Response(
            services.add_nursing_note(
                actor=request.user,
                facility=facility,
                admission_id=admission_id,
                data=request.data,
                request=request,
            )
        )


class DoctorOrderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, admission_id):
        facility = _facility(request)
        return Response(
            services.add_doctor_order(
                actor=request.user,
                facility=facility,
                admission_id=admission_id,
                data=request.data,
                request=request,
            )
        )


class MarView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, admission_id):
        facility = _facility(request)
        return Response(
            services.add_mar(
                actor=request.user,
                facility=facility,
                admission_id=admission_id,
                data=request.data,
                request=request,
            )
        )


class DischargeSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, admission_id):
        facility = _facility(request)
        return Response(
            services.save_discharge_summary(
                actor=request.user,
                facility=facility,
                admission_id=admission_id,
                data=request.data,
                request=request,
            )
        )


class SettlementPreviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, admission_id):
        facility = _facility(request)
        require_permission(request.user, facility, "ipd.read")
        return Response(services.settlement_preview(facility, admission_id))


class SettleView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, admission_id):
        facility = _facility(request)
        return Response(
            services.settle_and_discharge(
                actor=request.user,
                facility=facility,
                admission_id=admission_id,
                data=request.data,
                request=request,
            )
        )


class CancelDischargeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, admission_id):
        facility = _facility(request)
        return Response(
            services.cancel_discharge(
                actor=request.user,
                facility=facility,
                admission_id=admission_id,
                data=request.data,
                request=request,
            )
        )


class CancelAdmissionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, admission_id):
        facility = _facility(request)
        return Response(
            services.cancel_admission(
                actor=request.user,
                facility=facility,
                admission_id=admission_id,
                data=request.data,
                request=request,
            )
        )


class CertificateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "ipd.read")
        return Response(
            {
                "kinds": [{"value": c.value, "label": c.label} for c in CertificateKind],
                "items": services.list_certificates(
                    facility, admission_id=request.query_params.get("admission_id") or ""
                ),
            }
        )

    def post(self, request):
        facility = _facility(request)
        return Response(
            services.issue_certificate(
                actor=request.user, facility=facility, data=request.data, request=request
            ),
            status=201,
        )


class DischargePdfView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, admission_id):
        facility = _facility(request)
        require_permission(request.user, facility, "ipd.read")
        from apps.ipd.models import IpDischargeSummary

        admission = services._admission(facility, admission_id)
        try:
            _ = admission.discharge_summary
        except IpDischargeSummary.DoesNotExist as exc:
            raise AppError("Discharge summary not saved.", code="not_found") from exc
        content = pdfs.render_discharge_summary_pdf(admission)
        response = HttpResponse(content, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{admission.ip_no}-discharge.pdf"'
        return response


class CertificatePdfView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, cert_id):
        facility = _facility(request)
        require_permission(request.user, facility, "ipd.read")
        from apps.ipd.models import MedicalCertificate

        try:
            cert = MedicalCertificate.objects.select_related(
                "patient", "admission", "issued_by", "facility"
            ).get(id=cert_id, facility=facility)
        except MedicalCertificate.DoesNotExist as exc:
            raise AppError("Certificate not found.", code="not_found") from exc
        content = pdfs.render_certificate_pdf(cert)
        response = HttpResponse(content, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{cert.cert_no}.pdf"'
        return response
