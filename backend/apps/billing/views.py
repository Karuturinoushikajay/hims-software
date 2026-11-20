from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import require_permission
from apps.billing.models import Advance, Bill, CashShift, DiscountRequest, Refund, TaxCategory
from apps.billing.pdfs import render_bill_pdf
from apps.billing.serializers import (
    AdvanceSerializer,
    AmountSerializer,
    ApplyAdvanceSerializer,
    AuthorizeSerializer,
    CancelSerializer,
    ChargeSerializer,
    CollectDueSerializer,
    CountedCashSerializer,
    CreditNoteSerializer,
    DiscountRequestSerializer,
    OpeningCashSerializer,
    RefundSerializer,
)
from apps.billing.services import bill_payload, collect_due, post_service_charge
from apps.billing.settlement import (
    advance_payload,
    apply_advance,
    authorize_refund,
    cancel_bill,
    close_day,
    close_shift,
    decide_discount_request,
    discount_payload,
    issue_credit_note,
    open_shift,
    refund_advance,
    refund_payload,
    reopen_day,
    request_refund,
    shift_payload,
    submit_discount_request,
    take_advance,
)
from apps.common.exceptions import AppError
from apps.patients.models import Patient


def _facility(request):
    facility = getattr(request, "facility", None)
    if not facility:
        raise AppError("No active facility.", code="no_facility")
    return facility


def _bill(request, bill_id) -> Bill:
    facility = _facility(request)
    return Bill.objects.get(id=bill_id, facility=facility)


class TaxCategoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "billing.read")
        rows = TaxCategory.objects.filter(facility=facility, is_active=True)
        return Response(
            [
                {
                    "id": str(row.id),
                    "name": row.name,
                    "hsn_sac": row.hsn_sac,
                    "rate_percent": str(row.rate_percent),
                    "gst_confirmed": facility.settings.gstin_confirmed,
                }
                for row in rows
            ]
        )


class ChargeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        facility = _facility(request)
        ser = ChargeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        patient = Patient.objects.get(id=data["patient_id"], organization=facility.organization)
        rate = 0
        if data.get("tax_category_id"):
            category = TaxCategory.objects.get(id=data["tax_category_id"], facility=facility, is_active=True)
            rate = category.rate_percent
        bill = post_service_charge(
            facility=facility,
            patient=patient,
            actor=request.user,
            description=data["description"],
            amount=data["amount"],
            hospital_share=data["hospital_share"],
            doctor_share=data["doctor_share"],
            tax_rate=rate,
            discount_type=data.get("discount_type") or "NONE",
            discount_value=data.get("discount_value") or 0,
            paid=data.get("paid_amount"),
            payment_mode=data.get("mode") or "CASH",
            idempotency_key=request.headers.get("Idempotency-Key", ""),
        )
        payload = bill_payload(bill)
        payload["gst_confirmed"] = facility.settings.gstin_confirmed
        return Response(payload, status=201)


class BillListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "billing.read")
        qs = Bill.objects.filter(facility=facility).select_related("patient")
        patient_id = request.query_params.get("patient_id")
        if patient_id:
            qs = qs.filter(patient_id=patient_id)
        rows = []
        for bill in qs.order_by("-created_at")[:50]:
            if request.query_params.get("open") == "1" and bill.due_amount <= 0 and bill.status != "REFUND_DUE":
                continue
            rows.append(bill_payload(bill))
        return Response(rows)


class BillDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, bill_id):
        facility = _facility(request)
        require_permission(request.user, facility, "billing.read")
        return Response(bill_payload(_bill(request, bill_id)))


class BillPdfView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, bill_id):
        facility = _facility(request)
        require_permission(request.user, facility, "billing.read")
        bill = _bill(request, bill_id)
        layout = request.query_params.get("layout", "a4")
        document = request.query_params.get("doc", "invoice")
        if layout not in ("a4", "thermal") or document not in ("invoice", "receipt"):
            raise AppError("Unknown print layout.", code="bad_print")
        payload = render_bill_pdf(bill, layout, document)
        response = HttpResponse(payload, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{bill.bill_no}.pdf"'
        return response


class CollectDueView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "billing.collect")
        ser = CollectDueSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        bill = collect_due(
            bill=_bill(request, ser.validated_data["bill_id"]),
            actor=request.user,
            amount=ser.validated_data["amount"],
            mode=ser.validated_data["mode"],
            idempotency_key=request.headers.get("Idempotency-Key", ""),
        )
        return Response(bill_payload(bill))


class AdvanceListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "billing.read")
        qs = Advance.objects.filter(facility=facility).select_related("receipt", "patient")
        patient_id = request.query_params.get("patient_id")
        if patient_id:
            qs = qs.filter(patient_id=patient_id)
        return Response([advance_payload(row) for row in qs.order_by("-created_at")[:50]])

    def post(self, request):
        facility = _facility(request)
        ser = AdvanceSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        patient = Patient.objects.get(id=ser.validated_data["patient_id"], organization=facility.organization)
        row = take_advance(
            facility=facility,
            patient=patient,
            actor=request.user,
            amount=ser.validated_data["amount"],
            mode=ser.validated_data["mode"],
            idempotency_key=request.headers.get("Idempotency-Key", ""),
        )
        return Response(advance_payload(row), status=201)


class ApplyAdvanceView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, advance_id):
        facility = _facility(request)
        advance = Advance.objects.get(id=advance_id, facility=facility)
        ser = ApplyAdvanceSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        bill = apply_advance(
            advance=advance,
            bill=_bill(request, ser.validated_data["bill_id"]),
            actor=request.user,
            amount=ser.validated_data["amount"],
            idempotency_key=request.headers.get("Idempotency-Key", ""),
        )
        return Response(bill_payload(bill))


class RefundAdvanceView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, advance_id):
        facility = _facility(request)
        advance = Advance.objects.get(id=advance_id, facility=facility)
        ser = AmountSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        row = refund_advance(
            advance=advance,
            actor=request.user,
            amount=ser.validated_data["amount"],
            idempotency_key=request.headers.get("Idempotency-Key", ""),
        )
        return Response(advance_payload(row))


class RefundListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "billing.read")
        qs = Refund.objects.filter(facility=facility, status=Refund.Status.PENDING)
        return Response([refund_payload(row) for row in qs[:50]])

    def post(self, request):
        ser = RefundSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        row = request_refund(
            bill=_bill(request, ser.validated_data["bill_id"]),
            actor=request.user,
            amount=ser.validated_data["amount"],
            mode=ser.validated_data["mode"],
            reason=ser.validated_data["reason"],
            idempotency_key=request.headers.get("Idempotency-Key", ""),
        )
        return Response(refund_payload(row), status=201)


class AuthorizeRefundView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, refund_id):
        facility = _facility(request)
        refund = Refund.objects.get(id=refund_id, facility=facility)
        ser = AuthorizeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        row = authorize_refund(refund=refund, actor=request.user, approve=ser.validated_data["approve"])
        return Response(refund_payload(row))


class CreditNoteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = CreditNoteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        note = issue_credit_note(
            bill=_bill(request, ser.validated_data["bill_id"]),
            actor=request.user,
            amount=ser.validated_data["amount"],
            reason=ser.validated_data["reason"],
            idempotency_key=request.headers.get("Idempotency-Key", ""),
        )
        return Response(
            {"credit_note_no": note.credit_note_no, "amount": str(note.amount), "bill": bill_payload(note.bill)},
            status=201,
        )


class CancelBillView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, bill_id):
        ser = CancelSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        result = cancel_bill(
            bill=_bill(request, bill_id),
            actor=request.user,
            reason=ser.validated_data["reason"],
            mode=ser.validated_data["mode"],
        )
        bill = _bill(request, bill_id)
        return Response(
            {
                "bill": bill_payload(bill),
                "credit_note_no": result["credit_note"].credit_note_no if result["credit_note"] else "",
                "refund": refund_payload(result["refund"]) if result["refund"] else None,
            }
        )


class ShiftView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "billing.collect")
        shift = CashShift.objects.filter(
            facility=facility, user=request.user, status=CashShift.Status.OPEN
        ).first()
        return Response({"shift": shift_payload(shift) if shift else None})

    def post(self, request):
        facility = _facility(request)
        ser = OpeningCashSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        shift = open_shift(facility=facility, actor=request.user, opening_cash=ser.validated_data["opening_cash"])
        return Response(shift_payload(shift), status=201)


class CloseShiftView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        facility = _facility(request)
        ser = CountedCashSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        shift = close_shift(facility=facility, actor=request.user, counted_cash=ser.validated_data["counted_cash"])
        return Response(shift_payload(shift))


class DayCloseView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        facility = _facility(request)
        if request.data.get("reopen"):
            row = reopen_day(facility=facility, actor=request.user)
        else:
            row = close_day(facility=facility, actor=request.user)
        return Response(
            {
                "business_date": row.business_date.isoformat(),
                "reopened": bool(row.reopened_at),
                "snapshot": row.snapshot,
            }
        )


class DiscountRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = _facility(request)
        require_permission(request.user, facility, "billing.discount_authorize")
        rows = DiscountRequest.objects.filter(facility=facility, status=DiscountRequest.Status.PENDING)
        return Response([discount_payload(row) for row in rows.select_related("patient", "requested_by")[:50]])

    def post(self, request):
        facility = _facility(request)
        ser = DiscountRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        row = submit_discount_request(facility=facility, actor=request.user, data=ser.validated_data)
        return Response(discount_payload(row), status=201)


class DecideDiscountView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, request_id):
        facility = _facility(request)
        row = DiscountRequest.objects.get(id=request_id, facility=facility)
        ser = AuthorizeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        decided = decide_discount_request(request_row=row, actor=request.user, approve=ser.validated_data["approve"])
        return Response(discount_payload(decided))
