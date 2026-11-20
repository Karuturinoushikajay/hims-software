"""Advances, refunds, credit notes, shifts, and day close.

Posted bills stay unchanged. Each of these writes a new document.
GST is calculated in post_bill. TDS commission is calculated in commission.py.
"""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.accounts.permissions import require_permission, user_has_permission
from apps.audit.services import record_audit
from apps.billing.models import (
    Advance,
    AdvanceApplication,
    Bill,
    CashShift,
    CreditNote,
    DayClose,
    DiscountRequest,
    Payment,
    PaymentMode,
    Receipt,
    Refund,
)
from apps.billing.services import (
    _add_payment,
    _assert_discount_allowed,
    compute_discount,
    facility_today,
)
from apps.common.exceptions import AppError
from apps.common.money import money
from apps.numbering.models import DocumentType
from apps.numbering.services import allocate


def _tz(facility):
    return ZoneInfo(facility.timezone or "Asia/Kolkata")


def _day_bounds(facility, on_date):
    tz = _tz(facility)
    start = datetime.combine(on_date, time.min, tzinfo=tz)
    end = datetime.combine(on_date, time.max, tzinfo=tz)
    return start, end


def assert_business_day_open(facility, on_date=None) -> None:
    on_date = on_date or facility_today(facility)
    closed = DayClose.objects.filter(
        facility=facility, business_date=on_date, reopened_at__isnull=True
    ).exists()
    if closed:
        raise AppError(f"{on_date.isoformat()} is closed for this facility.", code="day_closed")


def _lock_bill(bill: Bill) -> Bill:
    return Bill.objects.select_for_update().get(pk=bill.pk)


def advance_payload(row: Advance) -> dict:
    return {
        "id": str(row.id),
        "advance_no": row.advance_no,
        "amount": str(row.amount),
        "balance": str(row.balance),
        "mode": row.mode,
        "receipt_no": row.receipt.receipt_no,
        "patient_id": str(row.patient_id),
    }


@transaction.atomic
def take_advance(*, facility, patient, actor, amount: Decimal, mode: str, idempotency_key: str = "") -> Advance:
    require_permission(actor, facility, "billing.collect")
    if idempotency_key:
        existing = Advance.objects.filter(facility=facility, idempotency_key=idempotency_key).first()
        if existing:
            return existing
    assert_business_day_open(facility)
    amount = money(amount)
    if amount <= 0:
        raise AppError("Advance must be greater than 0.", code="bad_payment")
    if mode not in PaymentMode.values or mode == PaymentMode.ADVANCE:
        raise AppError("Unknown payment mode.", code="bad_payment")
    number = allocate(document_type=DocumentType.ADV, facility=facility)
    receipt_no = allocate(document_type=DocumentType.RCPT, facility=facility)
    receipt = Receipt.objects.create(facility=facility, receipt_no=receipt_no, received_by=actor)
    row = Advance.objects.create(
        facility=facility,
        patient=patient,
        advance_no=number,
        amount=amount,
        mode=mode,
        receipt=receipt,
        idempotency_key=idempotency_key or "",
        received_by=actor,
    )
    record_audit(
        action="billing.advance",
        actor=actor,
        facility=facility,
        entity_type="Advance",
        entity_id=str(row.id),
        after={"advance_no": number, "amount": str(amount), "uhid": patient.uhid},
    )
    return row


@transaction.atomic
def apply_advance(*, advance: Advance, bill: Bill, actor, amount: Decimal, idempotency_key: str = "") -> Bill:
    require_permission(actor, advance.facility, "billing.collect")
    if idempotency_key:
        existing = AdvanceApplication.objects.filter(advance=advance, idempotency_key=idempotency_key).first()
        if existing and existing.bill_id:
            return existing.bill
    assert_business_day_open(advance.facility)
    if advance.patient_id != bill.patient_id or advance.facility_id != bill.facility_id:
        raise AppError("This advance belongs to a different patient or facility.", code="bad_advance")
    advance = Advance.objects.select_for_update().get(pk=advance.pk)
    bill = _lock_bill(bill)
    amount = money(amount)
    if amount <= 0 or amount > money(advance.balance):
        raise AppError("Amount must be within the advance balance.", code="bad_payment")
    if amount > money(bill.due_amount):
        raise AppError("Amount is more than the amount due.", code="bad_payment")
    if money(bill.due_amount) <= 0:
        raise AppError("This bill has nothing due.", code="bad_payment")
    application = AdvanceApplication.objects.create(
        advance=advance,
        bill=bill,
        kind=AdvanceApplication.Kind.APPLY,
        amount=amount,
        idempotency_key=idempotency_key or "",
        actor=actor,
    )
    _add_payment(
        bill=bill,
        actor=actor,
        amount=amount,
        mode=PaymentMode.ADVANCE,
        idempotency_key=f"advance:{application.id}",
    )
    record_audit(
        action="billing.advance.apply",
        actor=actor,
        facility=bill.facility,
        entity_type="Bill",
        entity_id=str(bill.id),
        after={"advance_no": advance.advance_no, "amount": str(amount), "bill_no": bill.bill_no},
    )
    bill.refresh_from_db()
    return bill


@transaction.atomic
def refund_advance(*, advance: Advance, actor, amount: Decimal, idempotency_key: str = "") -> Advance:
    require_permission(actor, advance.facility, "billing.refund")
    if idempotency_key:
        existing = AdvanceApplication.objects.filter(advance=advance, idempotency_key=idempotency_key).first()
        if existing:
            return advance
    assert_business_day_open(advance.facility)
    advance = Advance.objects.select_for_update().get(pk=advance.pk)
    amount = money(amount)
    if amount <= 0 or amount > money(advance.balance):
        raise AppError("Amount must be within the advance balance.", code="bad_payment")
    threshold = money(advance.facility.settings.refund_auth_threshold)
    if amount > threshold and not user_has_permission(actor, advance.facility, "billing.authorize_refund"):
        raise AppError(
            f"Refunds above {threshold} need a user who can authorize refunds.",
            code="refund_not_authorized",
        )
    AdvanceApplication.objects.create(
        advance=advance,
        kind=AdvanceApplication.Kind.REFUND,
        amount=amount,
        idempotency_key=idempotency_key or "",
        actor=actor,
    )
    record_audit(
        action="billing.advance.refund",
        actor=actor,
        facility=advance.facility,
        entity_type="Advance",
        entity_id=str(advance.id),
        after={"advance_no": advance.advance_no, "amount": str(amount)},
    )
    advance.refresh_from_db()
    return advance


def refund_payload(row: Refund) -> dict:
    return {
        "id": str(row.id),
        "refund_no": row.refund_no,
        "bill_id": str(row.bill_id),
        "amount": str(row.amount),
        "mode": row.mode,
        "status": row.status,
        "reason": row.reason,
    }


@transaction.atomic
def request_refund(*, bill: Bill, actor, amount: Decimal, mode: str, reason: str, idempotency_key: str = "") -> Refund:
    require_permission(actor, bill.facility, "billing.refund")
    if idempotency_key:
        existing = Refund.objects.filter(facility=bill.facility, idempotency_key=idempotency_key).first()
        if existing:
            return existing
    assert_business_day_open(bill.facility)
    if mode not in PaymentMode.values or mode == PaymentMode.ADVANCE:
        raise AppError("Unknown payment mode.", code="bad_payment")
    if not reason.strip():
        raise AppError("A refund needs a reason.", code="bad_refund")
    bill = _lock_bill(bill)
    amount = money(amount)
    retained = money(bill.paid_amount)
    if amount <= 0 or amount > retained:
        raise AppError("Refund must be greater than 0 and not more than the amount held.", code="bad_refund")
    threshold = money(bill.facility.settings.refund_auth_threshold)
    can_authorize = user_has_permission(actor, bill.facility, "billing.authorize_refund")
    needs_auth = amount > threshold and not can_authorize
    row = Refund.objects.create(
        facility=bill.facility,
        bill=bill,
        amount=amount,
        mode=mode,
        reason=reason.strip(),
        status=Refund.Status.PENDING,
        idempotency_key=idempotency_key or "",
        requested_by=actor,
    )
    if not needs_auth:
        _mark_refund_posted(row, actor)
    record_audit(
        action="billing.refund",
        actor=actor,
        facility=bill.facility,
        entity_type="Refund",
        entity_id=str(row.id),
        after={"amount": str(amount), "status": row.status, "bill_no": bill.bill_no},
    )
    row.refresh_from_db()
    return row


def _mark_refund_posted(row: Refund, actor) -> None:
    row.refund_no = allocate(document_type=DocumentType.REF, facility=row.facility)
    row.status = Refund.Status.POSTED
    row.authorized_by = actor
    row.posted_at = timezone.now()
    row.save()


@transaction.atomic
def authorize_refund(*, refund: Refund, actor, approve: bool) -> Refund:
    require_permission(actor, refund.facility, "billing.authorize_refund")
    refund = Refund.objects.select_for_update().get(pk=refund.pk)
    if refund.status != Refund.Status.PENDING:
        raise AppError("This refund is already decided.", code="bad_refund")
    if approve:
        assert_business_day_open(refund.facility)
        bill = _lock_bill(refund.bill)
        if money(refund.amount) > money(bill.paid_amount):
            raise AppError("The bill no longer holds this amount.", code="bad_refund")
        _mark_refund_posted(refund, actor)
    else:
        refund.status = Refund.Status.REJECTED
        refund.authorized_by = actor
        refund.save()
    record_audit(
        action="billing.refund.authorize",
        actor=actor,
        facility=refund.facility,
        entity_type="Refund",
        entity_id=str(refund.id),
        after={"status": refund.status, "refund_no": refund.refund_no},
    )
    refund.refresh_from_db()
    return refund


@transaction.atomic
def issue_credit_note(*, bill: Bill, actor, amount: Decimal, reason: str, idempotency_key: str = "") -> CreditNote:
    require_permission(actor, bill.facility, "billing.refund")
    if idempotency_key:
        existing = CreditNote.objects.filter(facility=bill.facility, idempotency_key=idempotency_key).first()
        if existing:
            return existing
    assert_business_day_open(bill.facility)
    if not reason.strip():
        raise AppError("A credit note needs a reason.", code="bad_credit")
    bill = _lock_bill(bill)
    amount = money(amount)
    remaining = money(bill.net_amount - bill.credited_amount)
    if amount <= 0 or amount > remaining:
        raise AppError("Credit must be greater than 0 and not more than the remaining bill.", code="bad_credit")
    number = allocate(document_type=DocumentType.CN, facility=bill.facility)
    note = CreditNote.objects.create(
        facility=bill.facility,
        bill=bill,
        credit_note_no=number,
        amount=amount,
        reason=reason.strip(),
        idempotency_key=idempotency_key or "",
        issued_by=actor,
    )
    record_audit(
        action="billing.credit_note",
        actor=actor,
        facility=bill.facility,
        entity_type="CreditNote",
        entity_id=str(note.id),
        after={"credit_note_no": number, "amount": str(amount), "bill_no": bill.bill_no},
    )
    return note


@transaction.atomic
def cancel_bill(*, bill: Bill, actor, reason: str, mode: str = PaymentMode.CASH) -> dict:
    """Credit whatever is still payable, then refund whatever cash is still held."""
    require_permission(actor, bill.facility, "billing.refund")
    assert_business_day_open(bill.facility)
    bill = _lock_bill(bill)
    remaining = money(bill.net_amount - bill.credited_amount)
    note = None
    if remaining > 0:
        note = issue_credit_note(bill=bill, actor=actor, amount=remaining, reason=reason)
        bill.refresh_from_db()
    refund = None
    held = money(bill.paid_amount)
    if held > 0:
        refund = request_refund(bill=bill, actor=actor, amount=held, mode=mode, reason=reason)
    from apps.billing.commission import reverse_commissions

    reverse_commissions(bill)
    record_audit(
        action="billing.cancel",
        actor=actor,
        facility=bill.facility,
        entity_type="Bill",
        entity_id=str(bill.id),
        after={"bill_no": bill.bill_no, "reason": reason},
    )
    return {"credit_note": note, "refund": refund}


def _sum(qs, field: str = "amount") -> str:
    total = qs.aggregate(s=Sum(field))["s"] or Decimal("0.00")
    return str(money(total))


def day_snapshot(facility, on_date) -> dict:
    start, end = _day_bounds(facility, on_date)
    payments = Payment.objects.filter(bill__facility=facility, created_at__range=(start, end))
    by_mode = {
        mode: _sum(payments.filter(mode=mode))
        for mode in PaymentMode.values
    }
    refunds = Refund.objects.filter(
        facility=facility, status=Refund.Status.POSTED, posted_at__range=(start, end)
    )
    return {
        "business_date": on_date.isoformat(),
        "bills": Bill.objects.filter(facility=facility, created_at__range=(start, end)).count(),
        "bill_net": _sum(Bill.objects.filter(facility=facility, created_at__range=(start, end)), "net_amount"),
        "collections_by_mode": by_mode,
        "refunds": _sum(refunds),
        "advances": _sum(Advance.objects.filter(facility=facility, created_at__range=(start, end))),
        "credit_notes": _sum(CreditNote.objects.filter(facility=facility, created_at__range=(start, end))),
    }


@transaction.atomic
def close_day(*, facility, actor) -> DayClose:
    require_permission(actor, facility, "billing.day_close")
    on_date = facility_today(facility)
    if CashShift.objects.filter(facility=facility, status=CashShift.Status.OPEN).exists():
        raise AppError("Close every open shift before closing the day.", code="shift_open")
    if DayClose.objects.filter(facility=facility, business_date=on_date, reopened_at__isnull=True).exists():
        raise AppError("This day is already closed.", code="day_closed")
    row = DayClose.objects.create(
        facility=facility,
        business_date=on_date,
        closed_by=actor,
        snapshot=day_snapshot(facility, on_date),
    )
    record_audit(
        action="billing.day_close",
        actor=actor,
        facility=facility,
        entity_type="DayClose",
        entity_id=str(row.id),
        after=row.snapshot,
    )
    return row


@transaction.atomic
def reopen_day(*, facility, actor) -> DayClose:
    require_permission(actor, facility, "billing.day_close")
    on_date = facility_today(facility)
    row = DayClose.objects.select_for_update().filter(
        facility=facility, business_date=on_date, reopened_at__isnull=True
    ).first()
    if not row:
        raise AppError("Today is not closed.", code="day_open")
    row.reopened_at = timezone.now()
    row.reopened_by = actor
    row.save()
    record_audit(
        action="billing.day_reopen",
        actor=actor,
        facility=facility,
        entity_type="DayClose",
        entity_id=str(row.id),
        after={"business_date": on_date.isoformat()},
    )
    return row


def _shift_cash(shift: CashShift, until) -> tuple[Decimal, dict]:
    cash_in = Payment.objects.filter(
        bill__facility=shift.facility,
        received_by=shift.user,
        mode=PaymentMode.CASH,
        created_at__gte=shift.opened_at,
        created_at__lte=until,
    )
    advances = Advance.objects.filter(
        facility=shift.facility,
        received_by=shift.user,
        mode=PaymentMode.CASH,
        created_at__gte=shift.opened_at,
        created_at__lte=until,
    )
    refunds = Refund.objects.filter(
        facility=shift.facility,
        authorized_by=shift.user,
        status=Refund.Status.POSTED,
        mode=PaymentMode.CASH,
        posted_at__gte=shift.opened_at,
        posted_at__lte=until,
    )
    advance_refunds = AdvanceApplication.objects.filter(
        advance__facility=shift.facility,
        advance__mode=PaymentMode.CASH,
        actor=shift.user,
        kind=AdvanceApplication.Kind.REFUND,
        created_at__gte=shift.opened_at,
        created_at__lte=until,
    )
    collected = money(
        (cash_in.aggregate(s=Sum("amount"))["s"] or 0)
        + (advances.aggregate(s=Sum("amount"))["s"] or 0)
    )
    paid_out = money(
        (refunds.aggregate(s=Sum("amount"))["s"] or 0)
        + (advance_refunds.aggregate(s=Sum("amount"))["s"] or 0)
    )
    expected = money(shift.opening_cash + collected - paid_out)
    return expected, {
        "cash_collections": str(collected),
        "cash_refunds": str(paid_out),
        "expected_cash": str(expected),
    }


def shift_payload(shift: CashShift) -> dict:
    data = {
        "id": str(shift.id),
        "status": shift.status,
        "opening_cash": str(shift.opening_cash),
        "opened_at": shift.opened_at.isoformat(),
        "closed_at": shift.closed_at.isoformat() if shift.closed_at else None,
        "counted_cash": str(shift.counted_cash) if shift.counted_cash is not None else None,
        "expected_cash": str(shift.expected_cash) if shift.expected_cash is not None else None,
        "variance": str(shift.variance) if shift.variance is not None else None,
        "snapshot": shift.snapshot,
    }
    return data


@transaction.atomic
def open_shift(*, facility, actor, opening_cash: Decimal) -> CashShift:
    require_permission(actor, facility, "billing.collect")
    assert_business_day_open(facility)
    if CashShift.objects.filter(facility=facility, user=actor, status=CashShift.Status.OPEN).exists():
        raise AppError("You already have an open shift.", code="shift_open")
    opening_cash = money(opening_cash)
    if opening_cash < 0:
        raise AppError("Opening cash cannot be negative.", code="bad_payment")
    shift = CashShift.objects.create(facility=facility, user=actor, opening_cash=opening_cash)
    record_audit(
        action="billing.shift.open",
        actor=actor,
        facility=facility,
        entity_type="CashShift",
        entity_id=str(shift.id),
        after={"opening_cash": str(opening_cash)},
    )
    return shift


@transaction.atomic
def close_shift(*, facility, actor, counted_cash: Decimal) -> CashShift:
    require_permission(actor, facility, "billing.collect")
    shift = CashShift.objects.select_for_update().filter(
        facility=facility, user=actor, status=CashShift.Status.OPEN
    ).first()
    if not shift:
        raise AppError("You do not have an open shift.", code="shift_closed")
    counted_cash = money(counted_cash)
    if counted_cash < 0:
        raise AppError("Counted cash cannot be negative.", code="bad_payment")
    now = timezone.now()
    expected, snapshot = _shift_cash(shift, now)
    shift.status = CashShift.Status.CLOSED
    shift.closed_at = now
    shift.counted_cash = counted_cash
    shift.expected_cash = expected
    shift.variance = money(counted_cash - expected)
    shift.snapshot = snapshot
    shift.save()
    record_audit(
        action="billing.shift.close",
        actor=actor,
        facility=facility,
        entity_type="CashShift",
        entity_id=str(shift.id),
        after={"expected_cash": str(expected), "counted_cash": str(counted_cash), "variance": str(shift.variance)},
    )
    return shift


def _jsonable(data: dict) -> dict:
    out = {}
    for key, value in data.items():
        if isinstance(value, Decimal):
            out[key] = str(value)
        elif value is None:
            out[key] = None
        else:
            out[key] = str(value) if hasattr(value, "hex") else value
    return out


@transaction.atomic
def submit_discount_request(*, facility, actor, data: dict) -> DiscountRequest:
    require_permission(actor, facility, "opd.consult.create")
    from apps.masters.models import Doctor
    from apps.patients.models import Patient

    patient = Patient.objects.get(id=data["patient_id"], organization=facility.organization)
    doctor = Doctor.objects.get(id=data["doctor_id"], facility=facility, is_active=True)
    gross = money(doctor.consultation_fee)
    discount_type = data.get("discount_type") or "NONE"
    discount_value = data.get("discount_value") or 0
    discount_amount = compute_discount(gross, discount_type, discount_value)
    try:
        _assert_discount_allowed(actor, facility, gross, discount_type, discount_value, discount_amount)
    except AppError as exc:
        if exc.code != "discount_not_authorized":
            raise
    else:
        raise AppError(
            "This discount is within your limit. Save the consultation directly.",
            code="discount_allowed",
        )
    row = DiscountRequest.objects.create(
        facility=facility,
        patient=patient,
        kind=DiscountRequest.Kind.CONSULTATION,
        payload=_jsonable(data),
        discount_type=discount_type,
        discount_value=money(discount_value),
        requested_by=actor,
    )
    record_audit(
        action="billing.discount.request",
        actor=actor,
        facility=facility,
        entity_type="DiscountRequest",
        entity_id=str(row.id),
        after={"uhid": patient.uhid, "discount_type": discount_type, "discount_value": str(discount_value)},
    )
    return row


def discount_payload(row: DiscountRequest) -> dict:
    return {
        "id": str(row.id),
        "patient_name": row.patient.full_name,
        "uhid": row.patient.uhid,
        "discount_type": row.discount_type,
        "discount_value": str(row.discount_value),
        "status": row.status,
        "result_bill_no": row.result_bill_no,
        "requested_by": row.requested_by.username,
    }


@transaction.atomic
def decide_discount_request(*, request_row: DiscountRequest, actor, approve: bool) -> DiscountRequest:
    require_permission(actor, request_row.facility, "billing.discount_authorize")
    row = DiscountRequest.objects.select_for_update().get(pk=request_row.pk)
    if row.status != DiscountRequest.Status.PENDING:
        raise AppError("This request is already decided.", code="bad_discount")
    if not approve:
        row.status = DiscountRequest.Status.REJECTED
        row.decided_by = actor
        row.save()
    else:
        from apps.opd.services import create_consultation

        result = create_consultation(actor=actor, facility=row.facility, data=row.payload)
        row.status = DiscountRequest.Status.APPROVED
        row.decided_by = actor
        row.result_bill_no = (result.get("bill") or {}).get("bill_no", "")
        row.save()
    record_audit(
        action="billing.discount.decide",
        actor=actor,
        facility=row.facility,
        entity_type="DiscountRequest",
        entity_id=str(row.id),
        after={"status": row.status, "bill_no": row.result_bill_no},
    )
    return row
