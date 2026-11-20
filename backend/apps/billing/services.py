"""One billing engine. Posting, tax, and the shared bill payload live here."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db import IntegrityError, transaction

from apps.accounts.models import Membership
from apps.billing.models import Bill, BillLine, DiscountType, Payment, PaymentMode, Receipt
from apps.common.exceptions import AppError
from apps.common.money import money, zero
from apps.numbering.models import DocumentType
from apps.numbering.services import allocate, financial_year_label


@dataclass
class ChargeLine:
    source_type: str
    source_id: str
    description: str
    amount: Decimal
    hospital_share: Decimal
    doctor_share: Decimal
    tax_rate: Decimal = Decimal("0")


def _role_limits(user, facility) -> tuple[Decimal, Decimal]:
    if user.is_superuser:
        return Decimal("100"), Decimal("999999999.99")
    rows = Membership.objects.filter(
        user=user, facility=facility, is_active=True, deleted_at__isnull=True
    )
    percents = [r.role.max_discount_percent for r in rows]
    amounts = [r.role.max_discount_amount for r in rows]
    return (max(percents) if percents else Decimal("0"), max(amounts) if amounts else Decimal("0"))


def compute_discount(gross: Decimal, discount_type: str, discount_value: Decimal) -> Decimal:
    gross = money(gross)
    value = money(discount_value)
    if discount_type == DiscountType.NONE or value == 0:
        return zero()
    if discount_type == DiscountType.PERCENT:
        if value < 0 or value > 100:
            raise AppError("Discount percent must be between 0 and 100.", code="bad_discount")
        return money(gross * value / Decimal("100"))
    if discount_type == DiscountType.FLAT:
        if value < 0:
            raise AppError("Discount amount cannot be negative.", code="bad_discount")
        return value
    raise AppError("Unknown discount type.", code="bad_discount")


def split_discount(hospital: Decimal, doctor: Decimal, discount: Decimal) -> tuple[Decimal, Decimal]:
    """Discount reduces hospital share first, then doctor share."""
    hospital = money(hospital)
    doctor = money(doctor)
    discount = money(discount)
    from_hospital = min(discount, hospital)
    from_doctor = money(discount - from_hospital)
    if from_doctor > doctor:
        raise AppError("Discount exceeds the bill amount.", code="bad_discount")
    return from_hospital, from_doctor


def _assert_discount_allowed(user, facility, gross, discount_type, discount_value, discount_amount):
    max_percent, max_amount = _role_limits(user, facility)
    if discount_type == DiscountType.PERCENT and money(discount_value) > money(max_percent):
        raise AppError(
            f"Discount exceeds your limit of {max_percent}%.",
            code="discount_not_authorized",
        )
    if discount_type == DiscountType.FLAT and discount_amount > money(max_amount):
        raise AppError(
            f"Discount exceeds your limit of {max_amount}.",
            code="discount_not_authorized",
        )
    if discount_amount > money(gross):
        raise AppError("Discount exceeds the bill amount.", code="bad_discount")


def _line_taxes(lines: list[ChargeLine], gross: Decimal, discount_amount: Decimal, gst_on: bool):
    """Discount reduces taxable value. The last line absorbs the paise remainder."""
    remaining = discount_amount
    taxed = []
    total = zero()
    for index, line in enumerate(lines):
        if index == len(lines) - 1:
            line_discount = remaining
        elif gross == 0:
            line_discount = zero()
        else:
            line_discount = money(discount_amount * money(line.amount) / gross)
            remaining = money(remaining - line_discount)
        taxable = money(money(line.amount) - line_discount)
        rate = money(line.tax_rate) if gst_on else zero()
        tax = money(taxable * rate / Decimal("100"))
        taxed.append((rate, tax))
        total = money(total + tax)
    return taxed, total


def split_gst(tax: Decimal, intra_state: bool) -> tuple[Decimal, Decimal, Decimal]:
    """Intra-state splits CGST and SGST so they add back to the tax. Inter-state is IGST."""
    tax = money(tax)
    if tax == 0:
        return zero(), zero(), zero()
    if not intra_state:
        return zero(), zero(), tax
    cgst = money(tax / Decimal("2"))
    sgst = money(tax - cgst)
    return cgst, sgst, zero()


@transaction.atomic
def post_bill(
    *,
    facility,
    patient,
    actor,
    lines: list[ChargeLine],
    discount_type: str = DiscountType.NONE,
    discount_value: Decimal = Decimal("0"),
    paid: Decimal | None = None,
    payment_mode: str = PaymentMode.CASH,
    idempotency_key: str = "",
    place_of_supply: str = "",
) -> Bill:
    from apps.billing.settlement import assert_business_day_open

    if idempotency_key:
        existing = Bill.objects.filter(facility=facility, idempotency_key=idempotency_key).first()
        if existing:
            return existing
    assert_business_day_open(facility)

    if not lines:
        raise AppError("A bill needs at least one line.", code="empty_bill")
    for line in lines:
        if money(line.hospital_share) + money(line.doctor_share) != money(line.amount):
            raise AppError(
                f"Shares for '{line.description}' must add up to the amount.",
                code="bad_share",
            )

    gross = money(sum((line.amount for line in lines), Decimal("0")))
    hospital = money(sum((line.hospital_share for line in lines), Decimal("0")))
    doctor = money(sum((line.doctor_share for line in lines), Decimal("0")))
    discount_amount = compute_discount(gross, discount_type, discount_value)
    _assert_discount_allowed(actor, facility, gross, discount_type, discount_value, discount_amount)
    from_hospital, from_doctor = split_discount(hospital, doctor, discount_amount)
    gst_on = bool(facility.settings.gstin_confirmed)
    line_taxes, tax_total = _line_taxes(lines, gross, discount_amount, gst_on)
    supply = (place_of_supply or facility.state_code or "").strip()
    intra = supply == (facility.state_code or "").strip()
    cgst, sgst, igst = split_gst(tax_total, intra)
    net = money(gross - discount_amount + tax_total)
    paid = net if paid is None else money(paid)
    if paid < 0 or paid > net:
        raise AppError("Paid amount must be between 0 and the net amount.", code="bad_payment")
    if paid > 0 and (payment_mode not in PaymentMode.values or payment_mode == PaymentMode.ADVANCE):
        raise AppError("Unknown payment mode.", code="bad_payment")

    on_date = facility_today(facility)
    fy = financial_year_label(
        on_date,
        facility.settings.financial_year_start_month,
        facility.settings.financial_year_start_day,
    )
    try:
        with transaction.atomic():
            bill_no = allocate(document_type=DocumentType.BILL, facility=facility, on_date=on_date)
            bill = Bill.objects.create(
            facility=facility,
            patient=patient,
            bill_no=bill_no,
            financial_year=fy,
            idempotency_key=idempotency_key or "",
            discount_type=discount_type,
            discount_value=money(discount_value),
            gross_amount=gross,
            discount_amount=discount_amount,
            discount_from_hospital=from_hospital,
            discount_from_doctor=from_doctor,
            tax_amount=tax_total,
            cgst_amount=cgst,
            sgst_amount=sgst,
            igst_amount=igst,
            gst_applied=gst_on and tax_total > 0,
            net_amount=net,
            posted_by=actor,
            )
    except IntegrityError:
        if idempotency_key:
            return Bill.objects.get(facility=facility, idempotency_key=idempotency_key)
        raise

    for line, (rate, tax) in zip(lines, line_taxes, strict=True):
        BillLine.objects.create(
            bill=bill,
            source_type=line.source_type,
            source_id=line.source_id,
            description=line.description,
            amount=money(line.amount),
            hospital_share=money(line.hospital_share),
            doctor_share=money(line.doctor_share),
            tax_rate=rate,
            tax_amount=tax,
        )

    if paid > 0:
        _add_payment(bill=bill, actor=actor, amount=paid, mode=payment_mode, idempotency_key="")
    return bill


@transaction.atomic
def collect_due(*, bill: Bill, actor, amount: Decimal, mode: str, idempotency_key: str = "") -> Bill:
    from apps.billing.settlement import assert_business_day_open

    if idempotency_key:
        existing = Payment.objects.filter(bill=bill, idempotency_key=idempotency_key).first()
        if existing:
            return bill
    assert_business_day_open(bill.facility)
    bill = Bill.objects.select_for_update().get(pk=bill.pk)
    if mode == PaymentMode.ADVANCE:
        raise AppError("Use advance application to settle from an advance.", code="bad_payment")
    amount = money(amount)
    due = money(bill.due_amount)
    if amount <= 0 or amount > due:
        raise AppError("Collection must be greater than 0 and not more than the due.", code="bad_payment")
    if mode not in PaymentMode.values:
        raise AppError("Unknown payment mode.", code="bad_payment")
    _add_payment(bill=bill, actor=actor, amount=amount, mode=mode, idempotency_key=idempotency_key)
    from apps.audit.services import record_audit

    record_audit(
        action="billing.collect",
        actor=actor,
        facility=bill.facility,
        entity_type="Bill",
        entity_id=str(bill.id),
        after={"bill_no": bill.bill_no, "amount": str(amount), "mode": mode},
    )
    bill.refresh_from_db()
    return bill


def _add_payment(*, bill: Bill, actor, amount: Decimal, mode: str, idempotency_key: str) -> Payment:
    receipt_no = allocate(document_type=DocumentType.RCPT, facility=bill.facility)
    receipt = Receipt.objects.create(
        facility=bill.facility, receipt_no=receipt_no, received_by=actor
    )
    return Payment.objects.create(
        bill=bill,
        receipt=receipt,
        amount=money(amount),
        mode=mode,
        idempotency_key=idempotency_key or "",
        received_by=actor,
    )


@transaction.atomic
def post_service_charge(
    *,
    facility,
    patient,
    actor,
    description: str,
    amount: Decimal,
    hospital_share: Decimal,
    doctor_share: Decimal,
    tax_rate: Decimal = Decimal("0"),
    discount_type: str = DiscountType.NONE,
    discount_value: Decimal = Decimal("0"),
    paid: Decimal | None = None,
    payment_mode: str = PaymentMode.CASH,
    idempotency_key: str = "",
) -> Bill:
    from apps.accounts.permissions import require_permission

    require_permission(actor, facility, "billing.collect")
    rate = money(tax_rate) if facility.settings.gstin_confirmed else zero()
    return post_bill(
        facility=facility,
        patient=patient,
        actor=actor,
        lines=[
            ChargeLine(
                source_type="service",
                source_id="",
                description=description,
                amount=money(amount),
                hospital_share=money(hospital_share),
                doctor_share=money(doctor_share),
                tax_rate=rate,
            )
        ],
        discount_type=discount_type,
        discount_value=discount_value,
        paid=paid,
        payment_mode=payment_mode,
        idempotency_key=idempotency_key,
    )


def facility_today(facility):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(facility.timezone or "Asia/Kolkata")
    return datetime.now(tz).date()


def bill_payload(bill: Bill) -> dict:
    return {
        "id": str(bill.id),
        "bill_no": bill.bill_no,
        "gross_amount": str(bill.gross_amount),
        "discount_type": bill.discount_type,
        "discount_value": str(bill.discount_value),
        "discount_amount": str(bill.discount_amount),
        "tax_amount": str(bill.tax_amount),
        "cgst_amount": str(bill.cgst_amount),
        "sgst_amount": str(bill.sgst_amount),
        "igst_amount": str(bill.igst_amount),
        "gst_applied": bill.gst_applied,
        "net_amount": str(bill.net_amount),
        "paid_amount": str(bill.paid_amount),
        "credited_amount": str(bill.credited_amount),
        "refunded_amount": str(bill.refunded_amount),
        "due_amount": str(bill.due_amount),
        "status": bill.status,
        "patient_id": str(bill.patient_id),
        "patient_name": bill.patient.full_name,
        "uhid": bill.patient.uhid,
        "lines": [
            {
                "description": line.description,
                "amount": str(line.amount),
                "hospital_share": str(line.hospital_share),
                "doctor_share": str(line.doctor_share),
                "source_type": line.source_type,
                "tax_rate": str(line.tax_rate),
                "tax_amount": str(line.tax_amount),
            }
            for line in bill.lines.all()
        ],
        "receipts": [
            {"receipt_no": p.receipt.receipt_no, "amount": str(p.amount), "mode": p.mode}
            for p in bill.payments.select_related("receipt")
        ],
        "refunds": [
            {
                "id": str(row.id),
                "refund_no": row.refund_no,
                "amount": str(row.amount),
                "mode": row.mode,
                "status": row.status,
                "reason": row.reason,
            }
            for row in bill.refunds.all()
        ],
        "credit_notes": [
            {"credit_note_no": row.credit_note_no, "amount": str(row.amount), "reason": row.reason}
            for row in bill.credit_notes.all()
        ],
    }
