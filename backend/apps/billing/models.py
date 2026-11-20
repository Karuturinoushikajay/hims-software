from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.common.models import TimeStampedModel, UUIDModel


class DiscountType(models.TextChoices):
    NONE = "NONE", "No Discount"
    PERCENT = "PERCENT", "Percentage"
    FLAT = "FLAT", "Flat Amount"


class PaymentMode(models.TextChoices):
    CASH = "CASH", "Cash"
    CARD = "CARD", "Card"
    UPI = "UPI", "UPI"
    CHEQUE = "CHEQUE", "Cheque"
    TRANSFER = "TRANSFER", "Bank Transfer"
    ADVANCE = "ADVANCE", "Adjusted from advance"


class TaxCategory(UUIDModel, TimeStampedModel):
    """GST rate for a charge. Applied only after the facility GSTIN is confirmed."""

    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.CASCADE, related_name="tax_categories"
    )
    name = models.CharField(max_length=128)
    hsn_sac = models.CharField(max_length=16, blank=True, default="")
    rate_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["facility", "name"], name="uniq_tax_category_facility_name")
        ]


class Bill(UUIDModel, TimeStampedModel):
    """Posted bill. Header amounts are immutable. Money movement is other documents."""

    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="bills"
    )
    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.PROTECT, related_name="bills"
    )
    bill_no = models.CharField(max_length=64)
    financial_year = models.CharField(max_length=16)
    idempotency_key = models.CharField(max_length=128, blank=True, default="")
    discount_type = models.CharField(max_length=16, choices=DiscountType.choices, default=DiscountType.NONE)
    discount_value = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    gross_amount = models.DecimalField(max_digits=14, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    discount_from_hospital = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    discount_from_doctor = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    cgst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    sgst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    igst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    gst_applied = models.BooleanField(default=False)
    net_amount = models.DecimalField(max_digits=14, decimal_places=2)
    posted_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="posted_bills"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["facility", "bill_no"], name="uniq_bill_no_facility"),
            models.UniqueConstraint(
                fields=["facility", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_bill_idempotency",
            ),
        ]
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("Posted bills are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Posted bills cannot be deleted.")

    @property
    def credited_amount(self) -> Decimal:
        total = self.credit_notes.aggregate(s=models.Sum("amount"))["s"]
        return total or Decimal("0.00")

    @property
    def refunded_amount(self) -> Decimal:
        total = self.refunds.filter(status=Refund.Status.POSTED).aggregate(s=models.Sum("amount"))["s"]
        return total or Decimal("0.00")

    @property
    def collected_amount(self) -> Decimal:
        total = self.payments.aggregate(s=models.Sum("amount"))["s"]
        return total or Decimal("0.00")

    @property
    def paid_amount(self) -> Decimal:
        """Cash still held against this bill: collections minus posted refunds."""
        return self.collected_amount - self.refunded_amount

    @property
    def payable_amount(self) -> Decimal:
        return self.net_amount - self.credited_amount

    @property
    def due_amount(self) -> Decimal:
        return self.payable_amount - self.paid_amount

    @property
    def status(self) -> str:
        payable = self.payable_amount
        retained = self.paid_amount
        if self.credited_amount >= self.net_amount and retained <= 0:
            return "CANCELLED"
        if payable <= 0 and retained > 0:
            return "REFUND_DUE"
        if retained <= 0:
            return "POSTED"
        if retained < payable:
            return "PARTIALLY_PAID"
        return "PAID"


class BillLine(UUIDModel, TimeStampedModel):
    bill = models.ForeignKey(Bill, on_delete=models.PROTECT, related_name="lines")
    source_type = models.CharField(max_length=32)
    source_id = models.CharField(max_length=64, blank=True, default="")
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1.00"))
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    hospital_share = models.DecimalField(max_digits=14, decimal_places=2)
    doctor_share = models.DecimalField(max_digits=14, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("Bill lines are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Bill lines cannot be deleted.")


class Receipt(UUIDModel, TimeStampedModel):
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="receipts"
    )
    receipt_no = models.CharField(max_length=64)
    received_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="receipts"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["facility", "receipt_no"], name="uniq_receipt_no_facility")
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("Receipts are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Receipts cannot be deleted.")


class Payment(UUIDModel, TimeStampedModel):
    bill = models.ForeignKey(Bill, on_delete=models.PROTECT, related_name="payments")
    receipt = models.ForeignKey(Receipt, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    mode = models.CharField(max_length=16, choices=PaymentMode.choices)
    idempotency_key = models.CharField(max_length=128, blank=True, default="")
    received_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="payments"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["bill", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_payment_idempotency",
            )
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("Payments are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Payments cannot be deleted.")


class Advance(UUIDModel, TimeStampedModel):
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="advances"
    )
    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.PROTECT, related_name="advances"
    )
    advance_no = models.CharField(max_length=64)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    mode = models.CharField(max_length=16, choices=PaymentMode.choices)
    receipt = models.ForeignKey(Receipt, on_delete=models.PROTECT, related_name="advances")
    idempotency_key = models.CharField(max_length=128, blank=True, default="")
    received_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="advances_received"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["facility", "advance_no"], name="uniq_advance_no_facility"),
            models.UniqueConstraint(
                fields=["facility", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_advance_idempotency",
            ),
        ]
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("Advances are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Advances cannot be deleted.")

    @property
    def used_amount(self) -> Decimal:
        total = self.applications.aggregate(s=models.Sum("amount"))["s"]
        return total or Decimal("0.00")

    @property
    def balance(self) -> Decimal:
        return self.amount - self.used_amount


class AdvanceApplication(UUIDModel, TimeStampedModel):
    class Kind(models.TextChoices):
        APPLY = "APPLY", "Applied to bill"
        REFUND = "REFUND", "Refunded to patient"

    advance = models.ForeignKey(Advance, on_delete=models.PROTECT, related_name="applications")
    bill = models.ForeignKey(
        Bill, on_delete=models.PROTECT, null=True, blank=True, related_name="advance_applications"
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    idempotency_key = models.CharField(max_length=128, blank=True, default="")
    actor = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="advance_applications"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["advance", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_advance_application_idempotency",
            )
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("Advance applications are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Advance applications cannot be deleted.")


class Refund(UUIDModel, TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending authorization"
        POSTED = "POSTED", "Posted"
        REJECTED = "REJECTED", "Rejected"

    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="refunds"
    )
    bill = models.ForeignKey(Bill, on_delete=models.PROTECT, related_name="refunds")
    refund_no = models.CharField(max_length=64, blank=True, default="")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    mode = models.CharField(max_length=16, choices=PaymentMode.choices)
    reason = models.CharField(max_length=255)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    idempotency_key = models.CharField(max_length=128, blank=True, default="")
    requested_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="refunds_requested"
    )
    authorized_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="refunds_authorized",
    )
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_refund_idempotency",
            )
        ]
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            previous = Refund.objects.get(pk=self.pk)
            if previous.status != self.Status.PENDING:
                raise RuntimeError("Posted refunds are append-only.")
            if previous.amount != self.amount or previous.bill_id != self.bill_id:
                raise RuntimeError("Refund amount and bill cannot change.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Refunds cannot be deleted.")


class CreditNote(UUIDModel, TimeStampedModel):
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="credit_notes"
    )
    bill = models.ForeignKey(Bill, on_delete=models.PROTECT, related_name="credit_notes")
    credit_note_no = models.CharField(max_length=64)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.CharField(max_length=255)
    idempotency_key = models.CharField(max_length=128, blank=True, default="")
    issued_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="credit_notes"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "credit_note_no"], name="uniq_credit_note_no_facility"
            ),
            models.UniqueConstraint(
                fields=["facility", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_credit_note_idempotency",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("Credit notes are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Credit notes cannot be deleted.")


class CommissionEntry(UUIDModel, TimeStampedModel):
    class Party(models.TextChoices):
        REFERRAL = "REFERRAL", "Referral doctor"
        PRO = "PRO", "PRO"

    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="commissions"
    )
    bill = models.ForeignKey(Bill, on_delete=models.PROTECT, related_name="commissions")
    party_kind = models.CharField(max_length=16, choices=Party.choices)
    party_id = models.UUIDField()
    party_name = models.CharField(max_length=255)
    base_amount = models.DecimalField(max_digits=14, decimal_places=2)
    commission_amount = models.DecimalField(max_digits=14, decimal_places=2)
    tds_amount = models.DecimalField(max_digits=14, decimal_places=2)
    net_payable = models.DecimalField(max_digits=14, decimal_places=2)
    reversal_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversals"
    )

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("Commission entries are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Commission entries cannot be deleted.")


class CashShift(UUIDModel, TimeStampedModel):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        CLOSED = "CLOSED", "Closed"

    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="cash_shifts"
    )
    user = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="cash_shifts"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    opening_cash = models.DecimalField(max_digits=14, decimal_places=2)
    opened_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    counted_cash = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    expected_cash = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    variance = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    snapshot = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "user"],
                condition=models.Q(status="OPEN"),
                name="uniq_open_shift_per_user",
            )
        ]


class DayClose(UUIDModel, TimeStampedModel):
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="day_closes"
    )
    business_date = models.DateField()
    closed_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="day_closes"
    )
    snapshot = models.JSONField(default=dict)
    reopened_at = models.DateTimeField(null=True, blank=True)
    reopened_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="day_reopens",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "business_date"],
                condition=models.Q(reopened_at__isnull=True),
                name="uniq_open_day_close",
            )
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            previous = DayClose.objects.get(pk=self.pk)
            if previous.reopened_at is not None:
                raise RuntimeError("A reopened day close cannot change again.")
            if previous.snapshot != self.snapshot or previous.business_date != self.business_date:
                raise RuntimeError("Day close totals are immutable.")
        return super().save(*args, **kwargs)


class DiscountRequest(UUIDModel, TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    class Kind(models.TextChoices):
        CONSULTATION = "CONSULTATION", "Consultation"

    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.CASCADE, related_name="discount_requests"
    )
    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.PROTECT, related_name="discount_requests"
    )
    kind = models.CharField(max_length=32, choices=Kind.choices)
    payload = models.JSONField(default=dict)
    discount_type = models.CharField(max_length=16)
    discount_value = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    requested_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="discount_requests"
    )
    decided_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="discount_decisions",
    )
    result_bill_no = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
