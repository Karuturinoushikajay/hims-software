"""Pharmacy stock and sales. FEFO dispensing; stock movements are append-only."""

from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.db.models import F, Sum

from apps.accounts.permissions import require_permission
from apps.audit.services import record_audit
from apps.billing.models import DiscountType, PaymentMode
from apps.billing.services import ChargeLine, bill_payload, facility_today, post_bill
from apps.clinical.models import Drug, Prescription
from apps.common.exceptions import AppError
from apps.common.money import money as as_money
from apps.common.money import zero
from apps.numbering.models import DocumentType
from apps.numbering.services import allocate
from apps.patients.models import Patient
from apps.pharmacy.models import (
    ControlledDrugEntry,
    GoodsReceipt,
    GoodsReceiptLine,
    PharmacyReturn,
    PharmacySale,
    PharmacySaleLine,
    PurchaseOrder,
    PurchaseOrderLine,
    StockBatch,
    StockMovement,
    Supplier,
)


def _drug(facility, drug_id) -> Drug:
    try:
        return Drug.objects.get(id=drug_id, facility=facility, is_active=True)
    except Drug.DoesNotExist as exc:
        raise AppError("Drug not found.", code="not_found") from exc


def _patient(facility, patient_id) -> Patient | None:
    if not patient_id:
        return None
    try:
        return Patient.objects.get(id=patient_id, organization=facility.organization)
    except Patient.DoesNotExist as exc:
        raise AppError("Patient not found.", code="not_found") from exc


def stock_on_hand(facility, drug_id=None) -> int:
    rows = StockBatch.objects.filter(facility=facility)
    if drug_id:
        rows = rows.filter(drug_id=drug_id)
    return rows.aggregate(total=Sum("quantity_on_hand"))["total"] or 0


def list_suppliers(facility):
    return [
        {
            "id": str(s.id),
            "name": s.name,
            "mobile": s.mobile,
            "gstin": s.gstin,
            "is_active": s.is_active,
        }
        for s in Supplier.objects.filter(facility=facility)
    ]


def create_supplier(*, actor, facility, data, request=None):
    require_permission(actor, facility, "pharmacy.write")
    name = (data.get("name") or "").strip()
    if not name:
        raise AppError("Supplier name is required.", code="invalid")
    row = Supplier.objects.create(
        facility=facility,
        name=name,
        mobile=(data.get("mobile") or "").strip(),
        gstin=(data.get("gstin") or "").strip(),
        address=(data.get("address") or "").strip(),
    )
    record_audit(
        action="pharmacy.supplier.create",
        actor=actor,
        facility=facility,
        entity_type="Supplier",
        entity_id=str(row.id),
        after={"name": name},
        request=request,
    )
    return {"id": str(row.id), "name": row.name}


def update_drug_pharmacy(*, actor, facility, drug_id, data, request=None):
    require_permission(actor, facility, "pharmacy.write")
    drug = _drug(facility, drug_id)
    for field in ("brand_name", "generic_name", "unit", "hsn_sac"):
        if field in data:
            setattr(drug, field, (data.get(field) or "").strip())
    if "schedule" in data:
        if data["schedule"] not in Drug.Schedule.values:
            raise AppError("Unknown schedule.", code="invalid")
        drug.schedule = data["schedule"]
    if "reorder_level" in data:
        drug.reorder_level = int(data["reorder_level"])
    if "purchase_price" in data:
        drug.purchase_price = as_money(data["purchase_price"])
    if "selling_price" in data:
        drug.selling_price = as_money(data["selling_price"])
    if "tax_rate" in data:
        drug.tax_rate = as_money(data["tax_rate"])
    drug.save()
    record_audit(
        action="pharmacy.drug.update",
        actor=actor,
        facility=facility,
        entity_type="Drug",
        entity_id=str(drug.id),
        after={"code": drug.code, "selling_price": str(drug.selling_price)},
        request=request,
    )
    return drug_payload(drug, facility)


def drug_payload(drug: Drug, facility) -> dict:
    on_hand = stock_on_hand(facility, drug.id)
    return {
        "id": str(drug.id),
        "code": drug.code,
        "name": drug.name,
        "brand_name": drug.brand_name or drug.name,
        "generic_name": drug.generic_name,
        "schedule": drug.schedule,
        "unit": drug.unit,
        "reorder_level": drug.reorder_level,
        "purchase_price": str(drug.purchase_price),
        "selling_price": str(drug.selling_price),
        "hsn_sac": drug.hsn_sac,
        "tax_rate": str(drug.tax_rate),
        "quantity_on_hand": on_hand,
        "below_reorder": on_hand < drug.reorder_level,
        "is_active": drug.is_active,
    }


def list_drugs(facility):
    return [drug_payload(d, facility) for d in Drug.objects.filter(facility=facility, is_active=True)]


def create_drug(*, actor, facility, data, request=None):
    require_permission(actor, facility, "pharmacy.write")
    code = (data.get("code") or "").strip().upper()
    name = (data.get("name") or "").strip()
    if not code or not name:
        raise AppError("Code and name are required.", code="invalid")
    if Drug.objects.filter(facility=facility, code=code).exists():
        raise AppError("A drug with that code already exists.", code="duplicate")
    drug = Drug.objects.create(
        facility=facility,
        code=code,
        name=name,
        brand_name=(data.get("brand_name") or name).strip(),
        generic_name=(data.get("generic_name") or "").strip(),
        schedule=data.get("schedule") or Drug.Schedule.NONE,
        unit=(data.get("unit") or "TAB").strip(),
        reorder_level=int(data.get("reorder_level") or 0),
        purchase_price=as_money(data.get("purchase_price") or 0),
        selling_price=as_money(data.get("selling_price") or 0),
        hsn_sac=(data.get("hsn_sac") or "").strip(),
        tax_rate=as_money(data.get("tax_rate") or 0),
    )
    record_audit(
        action="pharmacy.drug.create",
        actor=actor,
        facility=facility,
        entity_type="Drug",
        entity_id=str(drug.id),
        after={"code": code, "name": name},
        request=request,
    )
    return drug_payload(drug, facility)


@transaction.atomic
def create_purchase_order(*, actor, facility, data, request=None):
    require_permission(actor, facility, "pharmacy.purchase")
    try:
        supplier = Supplier.objects.get(id=data.get("supplier_id"), facility=facility, is_active=True)
    except Supplier.DoesNotExist as exc:
        raise AppError("Supplier not found.", code="not_found") from exc
    lines = data.get("lines") or []
    if not lines:
        raise AppError("Add at least one line.", code="invalid")
    po_no = allocate(document_type=DocumentType.PO, facility=facility, on_date=facility_today(facility))
    po = PurchaseOrder.objects.create(
        facility=facility,
        supplier=supplier,
        po_no=po_no,
        ordered_by=actor,
        remarks=(data.get("remarks") or "").strip(),
    )
    for row in lines:
        drug = _drug(facility, row.get("drug_id"))
        qty = int(row.get("quantity") or 0)
        if qty <= 0:
            raise AppError("Quantity must be positive.", code="invalid")
        PurchaseOrderLine.objects.create(
            purchase_order=po,
            drug=drug,
            quantity=qty,
            unit_cost=as_money(row.get("unit_cost") or drug.purchase_price),
        )
    record_audit(
        action="pharmacy.po.create",
        actor=actor,
        facility=facility,
        entity_type="PurchaseOrder",
        entity_id=str(po.id),
        after={"po_no": po_no},
        request=request,
    )
    return po_payload(po)


def po_payload(po: PurchaseOrder) -> dict:
    return {
        "id": str(po.id),
        "po_no": po.po_no,
        "status": po.status,
        "supplier": po.supplier.name,
        "supplier_id": str(po.supplier_id),
        "lines": [
            {
                "id": str(line.id),
                "drug_id": str(line.drug_id),
                "drug": line.drug.name,
                "quantity": line.quantity,
                "received_quantity": line.received_quantity,
                "unit_cost": str(line.unit_cost),
            }
            for line in po.lines.select_related("drug")
        ],
    }


def _write_movement(*, facility, batch, kind, delta, actor, reference="", remarks=""):
    StockMovement.objects.create(
        facility=facility,
        batch=batch,
        drug=batch.drug,
        kind=kind,
        quantity_delta=delta,
        reference=reference,
        remarks=remarks,
        actor=actor,
    )


@transaction.atomic
def receive_goods(*, actor, facility, data, request=None):
    require_permission(actor, facility, "pharmacy.purchase")
    try:
        supplier = Supplier.objects.get(id=data.get("supplier_id"), facility=facility, is_active=True)
    except Supplier.DoesNotExist as exc:
        raise AppError("Supplier not found.", code="not_found") from exc
    po = None
    if data.get("purchase_order_id"):
        try:
            po = PurchaseOrder.objects.select_for_update().get(
                id=data["purchase_order_id"], facility=facility
            )
        except PurchaseOrder.DoesNotExist as exc:
            raise AppError("Purchase order not found.", code="not_found") from exc
        if po.status == PurchaseOrder.Status.CANCELLED:
            raise AppError("Purchase order is cancelled.", code="invalid")
    lines = data.get("lines") or []
    if not lines:
        raise AppError("Add at least one receipt line.", code="invalid")
    grn_no = allocate(document_type=DocumentType.GRN, facility=facility, on_date=facility_today(facility))
    grn = GoodsReceipt.objects.create(
        facility=facility,
        supplier=supplier,
        purchase_order=po,
        grn_no=grn_no,
        received_by=actor,
        invoice_no=(data.get("invoice_no") or "").strip(),
    )
    today = facility_today(facility)
    for row in lines:
        drug = _drug(facility, row.get("drug_id"))
        qty = int(row.get("quantity") or 0)
        batch_no = (row.get("batch_no") or "").strip().upper()
        expiry = row.get("expiry_date")
        if hasattr(expiry, "isoformat"):
            expiry_date = expiry
        else:
            from django.utils.dateparse import parse_date

            expiry_date = parse_date(str(expiry or ""))
        if qty <= 0 or not batch_no or not expiry_date:
            raise AppError("Batch, expiry, and positive quantity are required.", code="invalid")
        if expiry_date <= today:
            raise AppError("Cannot receive an expired batch.", code="expired_batch")
        unit_cost = as_money(row.get("unit_cost") or drug.purchase_price)
        po_line = None
        if po and row.get("purchase_order_line_id"):
            po_line = PurchaseOrderLine.objects.select_for_update().get(
                id=row["purchase_order_line_id"], purchase_order=po
            )
            if po_line.received_quantity + qty > po_line.quantity:
                raise AppError("Received quantity exceeds the purchase order.", code="over_receipt")
            po_line.received_quantity = F("received_quantity") + qty
            po_line.save(update_fields=["received_quantity", "updated_at"])
            po_line.refresh_from_db()
        grn_line = GoodsReceiptLine.objects.create(
            goods_receipt=grn,
            drug=drug,
            batch_no=batch_no,
            expiry_date=expiry_date,
            quantity=qty,
            unit_cost=unit_cost,
            purchase_order_line=po_line,
        )
        batch, created = StockBatch.objects.select_for_update().get_or_create(
            facility=facility,
            drug=drug,
            batch_no=batch_no,
            expiry_date=expiry_date,
            defaults={"quantity_on_hand": 0, "unit_cost": unit_cost, "goods_receipt_line": grn_line},
        )
        batch.quantity_on_hand = batch.quantity_on_hand + qty
        batch.unit_cost = unit_cost
        batch.save(update_fields=["quantity_on_hand", "unit_cost", "updated_at"])
        _write_movement(
            facility=facility,
            batch=batch,
            kind=StockMovement.Kind.GRN,
            delta=qty,
            actor=actor,
            reference=grn_no,
        )
    if po:
        po.refresh_from_db()
        lines_qs = list(po.lines.all())
        if all(line.received_quantity >= line.quantity for line in lines_qs):
            po.status = PurchaseOrder.Status.CLOSED
        elif any(line.received_quantity > 0 for line in lines_qs):
            po.status = PurchaseOrder.Status.PARTIAL
        po.save(update_fields=["status", "updated_at"])
    record_audit(
        action="pharmacy.grn.create",
        actor=actor,
        facility=facility,
        entity_type="GoodsReceipt",
        entity_id=str(grn.id),
        after={"grn_no": grn_no},
        request=request,
    )
    return {"id": str(grn.id), "grn_no": grn_no}


def _fefo_allocate(facility, drug: Drug, quantity: int) -> list[tuple[StockBatch, int]]:
    if quantity <= 0:
        raise AppError("Quantity must be positive.", code="invalid")
    today = facility_today(facility)
    batches = list(
        StockBatch.objects.select_for_update()
        .filter(facility=facility, drug=drug, quantity_on_hand__gt=0, expiry_date__gt=today)
        .order_by("expiry_date", "created_at")
    )
    remaining = quantity
    allocated = []
    for batch in batches:
        take = min(batch.quantity_on_hand, remaining)
        if take <= 0:
            continue
        allocated.append((batch, take))
        remaining -= take
        if remaining == 0:
            break
    if remaining > 0:
        raise AppError(
            f"Insufficient stock for {drug.name}. Short by {remaining}.",
            code="insufficient_stock",
        )
    return allocated


@transaction.atomic
def sell(*, actor, facility, data, request=None):
    require_permission(actor, facility, "pharmacy.dispense")
    kind = data.get("kind") or PharmacySale.Kind.COUNTER
    if kind not in PharmacySale.Kind.values:
        raise AppError("Unknown sale kind.", code="invalid")
    patient = _patient(facility, data.get("patient_id"))
    prescription = None
    if data.get("prescription_id"):
        try:
            prescription = Prescription.objects.select_related("visit").get(
                id=data["prescription_id"], facility=facility
            )
        except Prescription.DoesNotExist as exc:
            raise AppError("Prescription not found.", code="not_found") from exc
        patient = patient or prescription.visit.patient
        kind = PharmacySale.Kind.PRESCRIPTION
    if kind == PharmacySale.Kind.IP_ISSUE and not patient:
        raise AppError("IP issue requires a patient.", code="invalid")
    items = data.get("items") or []
    if not items:
        raise AppError("Add at least one item.", code="invalid")

    idempotency_key = (data.get("idempotency_key") or "").strip()
    if idempotency_key:
        existing = PharmacySale.objects.filter(facility=facility, idempotency_key=idempotency_key).first()
        if existing:
            return sale_payload(existing)

    sale_no = allocate(document_type=DocumentType.PHARM, facility=facility, on_date=facility_today(facility))
    sale = PharmacySale.objects.create(
        facility=facility,
        sale_no=sale_no,
        kind=kind,
        patient=patient,
        prescription=prescription,
        sold_by=actor,
        idempotency_key=idempotency_key,
    )
    charge_lines = []
    for row in items:
        drug = _drug(facility, row.get("drug_id"))
        qty = int(row.get("quantity") or 0)
        allocations = _fefo_allocate(facility, drug, qty)
        unit_price = as_money(row.get("unit_price") or drug.selling_price)
        tax_rate = as_money(row.get("tax_rate") if row.get("tax_rate") is not None else drug.tax_rate)
        if not facility.settings.gstin_confirmed:
            tax_rate = zero()
        for batch, take in allocations:
            batch.quantity_on_hand -= take
            batch.save(update_fields=["quantity_on_hand", "updated_at"])
            movement_kind = (
                StockMovement.Kind.IP_ISSUE if kind == PharmacySale.Kind.IP_ISSUE else StockMovement.Kind.SALE
            )
            _write_movement(
                facility=facility,
                batch=batch,
                kind=movement_kind,
                delta=-take,
                actor=actor,
                reference=sale_no,
            )
            PharmacySaleLine.objects.create(
                sale=sale,
                drug=drug,
                batch=batch,
                quantity=take,
                unit_price=unit_price,
                tax_rate=tax_rate,
            )
            if drug.schedule in (Drug.Schedule.H1, Drug.Schedule.NARCOTIC):
                ControlledDrugEntry.objects.create(
                    facility=facility,
                    drug=drug,
                    batch=batch,
                    sale=sale,
                    patient=patient,
                    quantity=take,
                    schedule=drug.schedule,
                    recorded_by=actor,
                )
            line_amount = as_money(unit_price * take)
            charge_lines.append(
                ChargeLine(
                    source_type="pharmacy",
                    source_id=sale_no,
                    description=f"{drug.name} x {take}",
                    amount=line_amount,
                    hospital_share=line_amount,
                    doctor_share=zero(),
                    tax_rate=tax_rate,
                )
            )

    bill = None
    if patient and charge_lines:
        paid = data.get("paid_amount")
        if kind == PharmacySale.Kind.IP_ISSUE:
            paid = 0
        bill = post_bill(
            facility=facility,
            patient=patient,
            actor=actor,
            lines=charge_lines,
            discount_type=data.get("discount_type") or DiscountType.NONE,
            discount_value=data.get("discount_value") or 0,
            paid=paid,
            payment_mode=data.get("payment_mode") or PaymentMode.CASH,
            idempotency_key=f"pharm:{sale_no}",
        )
        sale.bill = bill
        sale.save(update_fields=["bill", "updated_at"])
    record_audit(
        action="pharmacy.sale",
        actor=actor,
        facility=facility,
        entity_type="PharmacySale",
        entity_id=str(sale.id),
        after={"sale_no": sale_no, "kind": kind},
        request=request,
    )
    return sale_payload(sale)


def sale_payload(sale: PharmacySale) -> dict:
    return {
        "id": str(sale.id),
        "sale_no": sale.sale_no,
        "kind": sale.kind,
        "patient_id": str(sale.patient_id) if sale.patient_id else "",
        "bill": bill_payload(sale.bill) if sale.bill_id else None,
        "lines": [
            {
                "id": str(line.id),
                "drug": line.drug.name,
                "batch_no": line.batch.batch_no,
                "expiry_date": line.batch.expiry_date.isoformat(),
                "quantity": line.quantity,
                "unit_price": str(line.unit_price),
                "tax_rate": str(line.tax_rate),
            }
            for line in sale.lines.select_related("drug", "batch")
        ],
    }


@transaction.atomic
def return_sale_line(*, actor, facility, data, request=None):
    require_permission(actor, facility, "pharmacy.dispense")
    try:
        line = PharmacySaleLine.objects.select_related("sale", "batch", "drug").get(
            id=data.get("sale_line_id"), sale__facility=facility
        )
    except PharmacySaleLine.DoesNotExist as exc:
        raise AppError("Sale line not found.", code="not_found") from exc
    qty = int(data.get("quantity") or 0)
    already = line.returns.aggregate(total=Sum("quantity"))["total"] or 0
    if qty <= 0 or already + qty > line.quantity:
        raise AppError("Return quantity is invalid.", code="invalid")
    batch = StockBatch.objects.select_for_update().get(pk=line.batch_id)
    batch.quantity_on_hand += qty
    batch.save(update_fields=["quantity_on_hand", "updated_at"])
    _write_movement(
        facility=facility,
        batch=batch,
        kind=StockMovement.Kind.RETURN,
        delta=qty,
        actor=actor,
        reference=line.sale.sale_no,
        remarks=(data.get("reason") or "").strip(),
    )
    row = PharmacyReturn.objects.create(
        facility=facility,
        sale=line.sale,
        sale_line=line,
        quantity=qty,
        reason=(data.get("reason") or "").strip(),
        returned_by=actor,
    )
    credit = None
    if line.sale.bill_id:
        from apps.billing.settlement import issue_credit_note

        amount = as_money(line.unit_price * qty)
        credit = issue_credit_note(
            bill=line.sale.bill,
            actor=actor,
            amount=amount,
            reason=f"Pharmacy return {line.drug.name} x {qty}",
            idempotency_key=f"pharm-ret:{row.id}",
        )
        row.credit_note = credit
        row.save(update_fields=["credit_note", "updated_at"])
    record_audit(
        action="pharmacy.return",
        actor=actor,
        facility=facility,
        entity_type="PharmacyReturn",
        entity_id=str(row.id),
        after={"quantity": qty, "drug": line.drug.name},
        request=request,
    )
    return {"id": str(row.id), "quantity": qty, "credit_note_id": str(credit.id) if credit else ""}


@transaction.atomic
def adjust_stock(*, actor, facility, data, request=None):
    require_permission(actor, facility, "pharmacy.adjust")
    kind = data.get("kind")
    if kind not in (StockMovement.Kind.ADJUST, StockMovement.Kind.DUMP):
        raise AppError("Kind must be ADJUST or DUMP.", code="invalid")
    try:
        batch = StockBatch.objects.select_for_update().get(id=data.get("batch_id"), facility=facility)
    except StockBatch.DoesNotExist as exc:
        raise AppError("Batch not found.", code="not_found") from exc
    qty = int(data.get("quantity") or 0)
    if qty <= 0:
        raise AppError("Quantity must be positive.", code="invalid")
    if kind == StockMovement.Kind.DUMP or data.get("direction") == "DOWN":
        if qty > batch.quantity_on_hand:
            raise AppError("Cannot dump more than on hand.", code="insufficient_stock")
        delta = -qty
    else:
        delta = qty
    batch.quantity_on_hand += delta
    batch.save(update_fields=["quantity_on_hand", "updated_at"])
    _write_movement(
        facility=facility,
        batch=batch,
        kind=kind,
        delta=delta,
        actor=actor,
        remarks=(data.get("remarks") or "").strip(),
    )
    record_audit(
        action="pharmacy.stock.adjust",
        actor=actor,
        facility=facility,
        entity_type="StockBatch",
        entity_id=str(batch.id),
        after={"delta": delta, "kind": kind},
        request=request,
    )
    return {
        "batch_id": str(batch.id),
        "quantity_on_hand": batch.quantity_on_hand,
        "delta": delta,
    }


def inventory_snapshot(facility, near_expiry_days: int = 30) -> dict:
    today = facility_today(facility)
    horizon = today + timedelta(days=near_expiry_days)
    drugs = list_drugs(facility)
    batches = [
        {
            "id": str(b.id),
            "drug_id": str(b.drug_id),
            "drug": b.drug.name,
            "batch_no": b.batch_no,
            "expiry_date": b.expiry_date.isoformat(),
            "quantity_on_hand": b.quantity_on_hand,
            "unit_cost": str(b.unit_cost),
            "near_expiry": b.expiry_date <= horizon,
            "expired": b.expiry_date <= today,
        }
        for b in StockBatch.objects.filter(facility=facility, quantity_on_hand__gt=0).select_related("drug")
    ]
    return {
        "drugs": drugs,
        "batches": batches,
        "low_stock": [d for d in drugs if d["below_reorder"]],
        "near_expiry": [b for b in batches if b["near_expiry"] and not b["expired"]],
        "controlled_register": [
            {
                "id": str(e.id),
                "drug": e.drug.name,
                "schedule": e.schedule,
                "quantity": e.quantity,
                "batch_no": e.batch.batch_no,
                "sale_no": e.sale.sale_no,
                "patient": e.patient.full_name if e.patient_id else "",
                "at": e.created_at.isoformat(),
            }
            for e in ControlledDrugEntry.objects.filter(facility=facility)
            .select_related("drug", "batch", "sale", "patient")
            .order_by("-created_at")[:50]
        ],
    }


def list_purchase_orders(facility):
    return [po_payload(po) for po in PurchaseOrder.objects.filter(facility=facility).select_related("supplier")]
