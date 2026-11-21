from __future__ import annotations

from decimal import Decimal

from django.db import models

from apps.common.models import TimeStampedModel, UUIDModel


class Supplier(UUIDModel, TimeStampedModel):
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.CASCADE, related_name="suppliers"
    )
    name = models.CharField(max_length=255)
    mobile = models.CharField(max_length=20, blank=True, default="")
    gstin = models.CharField(max_length=20, blank=True, default="")
    address = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["facility", "name"], name="uniq_supplier_facility_name")
        ]


class PurchaseOrder(UUIDModel, TimeStampedModel):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        PARTIAL = "PARTIAL", "Partially received"
        CLOSED = "CLOSED", "Closed"
        CANCELLED = "CANCELLED", "Cancelled"

    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="purchase_orders"
    )
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchase_orders")
    po_no = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    ordered_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="purchase_orders"
    )
    remarks = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["facility", "po_no"], name="uniq_po_facility_no")
        ]


class PurchaseOrderLine(UUIDModel, TimeStampedModel):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    drug = models.ForeignKey("clinical.Drug", on_delete=models.PROTECT, related_name="po_lines")
    quantity = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    received_quantity = models.PositiveIntegerField(default=0)


class GoodsReceipt(UUIDModel, TimeStampedModel):
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="goods_receipts"
    )
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="goods_receipts")
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name="receipts"
    )
    grn_no = models.CharField(max_length=64)
    received_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="goods_receipts"
    )
    invoice_no = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["facility", "grn_no"], name="uniq_grn_facility_no")
        ]


class GoodsReceiptLine(UUIDModel, TimeStampedModel):
    goods_receipt = models.ForeignKey(GoodsReceipt, on_delete=models.CASCADE, related_name="lines")
    drug = models.ForeignKey("clinical.Drug", on_delete=models.PROTECT, related_name="grn_lines")
    batch_no = models.CharField(max_length=64)
    expiry_date = models.DateField()
    quantity = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    purchase_order_line = models.ForeignKey(
        PurchaseOrderLine, on_delete=models.SET_NULL, null=True, blank=True, related_name="receipts"
    )


class StockBatch(UUIDModel, TimeStampedModel):
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="stock_batches"
    )
    drug = models.ForeignKey("clinical.Drug", on_delete=models.PROTECT, related_name="batches")
    batch_no = models.CharField(max_length=64)
    expiry_date = models.DateField()
    quantity_on_hand = models.PositiveIntegerField(default=0)
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    goods_receipt_line = models.ForeignKey(
        GoodsReceiptLine, on_delete=models.SET_NULL, null=True, blank=True, related_name="batches"
    )

    class Meta:
        ordering = ["expiry_date", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "drug", "batch_no", "expiry_date"],
                name="uniq_stock_batch",
            )
        ]


class StockMovement(UUIDModel, TimeStampedModel):
    """Append-only stock ledger. Never update or delete after create."""

    class Kind(models.TextChoices):
        GRN = "GRN", "Goods receipt"
        SALE = "SALE", "Sale / issue"
        RETURN = "RETURN", "Customer return"
        ADJUST = "ADJUST", "Adjustment"
        DUMP = "DUMP", "Dump / write-off"
        IP_ISSUE = "IP_ISSUE", "IP issue"

    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="stock_movements"
    )
    batch = models.ForeignKey(StockBatch, on_delete=models.PROTECT, related_name="movements")
    drug = models.ForeignKey("clinical.Drug", on_delete=models.PROTECT, related_name="stock_movements")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    quantity_delta = models.IntegerField()
    reference = models.CharField(max_length=64, blank=True, default="")
    remarks = models.CharField(max_length=255, blank=True, default="")
    actor = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="stock_movements"
    )

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("Stock movements are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Stock movements cannot be deleted.")


class PharmacySale(UUIDModel, TimeStampedModel):
    class Kind(models.TextChoices):
        COUNTER = "COUNTER", "Counter sale"
        PRESCRIPTION = "PRESCRIPTION", "Against prescription"
        IP_ISSUE = "IP_ISSUE", "IP pharmacy issue"

    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="pharmacy_sales"
    )
    sale_no = models.CharField(max_length=64)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.COUNTER)
    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.PROTECT, null=True, blank=True, related_name="pharmacy_sales"
    )
    prescription = models.ForeignKey(
        "clinical.Prescription",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pharmacy_sales",
    )
    sold_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="pharmacy_sales"
    )
    bill = models.ForeignKey(
        "billing.Bill", on_delete=models.PROTECT, null=True, blank=True, related_name="pharmacy_sales"
    )
    idempotency_key = models.CharField(max_length=128, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["facility", "sale_no"], name="uniq_pharmacy_sale_no"),
            models.UniqueConstraint(
                fields=["facility", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_pharmacy_sale_idempotency",
            ),
        ]


class PharmacySaleLine(UUIDModel, TimeStampedModel):
    sale = models.ForeignKey(PharmacySale, on_delete=models.CASCADE, related_name="lines")
    drug = models.ForeignKey("clinical.Drug", on_delete=models.PROTECT, related_name="sale_lines")
    batch = models.ForeignKey(StockBatch, on_delete=models.PROTECT, related_name="sale_lines")
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))


class PharmacyReturn(UUIDModel, TimeStampedModel):
    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="pharmacy_returns"
    )
    sale = models.ForeignKey(PharmacySale, on_delete=models.PROTECT, related_name="returns")
    sale_line = models.ForeignKey(PharmacySaleLine, on_delete=models.PROTECT, related_name="returns")
    quantity = models.PositiveIntegerField()
    reason = models.CharField(max_length=255, blank=True, default="")
    returned_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="pharmacy_returns"
    )
    credit_note = models.ForeignKey(
        "billing.CreditNote",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pharmacy_returns",
    )


class ControlledDrugEntry(UUIDModel, TimeStampedModel):
    """Register line for schedule H1 / narcotic dispensing."""

    facility = models.ForeignKey(
        "organizations.Facility", on_delete=models.PROTECT, related_name="controlled_drug_entries"
    )
    drug = models.ForeignKey("clinical.Drug", on_delete=models.PROTECT, related_name="controlled_entries")
    batch = models.ForeignKey(StockBatch, on_delete=models.PROTECT, related_name="controlled_entries")
    sale = models.ForeignKey(PharmacySale, on_delete=models.PROTECT, related_name="controlled_entries")
    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.PROTECT, null=True, blank=True, related_name="controlled_entries"
    )
    quantity = models.PositiveIntegerField()
    schedule = models.CharField(max_length=16)
    recorded_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="controlled_drug_entries"
    )
