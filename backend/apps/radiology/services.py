"""Radiology RIS: test master, scheduling, reporting, consumables, PDF."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.accounts.permissions import require_permission
from apps.audit.services import record_audit
from apps.billing.models import DiscountType, PaymentMode
from apps.billing.services import ChargeLine, bill_payload, facility_today, post_bill
from apps.clinical.models import ClinicalOrder
from apps.common.exceptions import AppError
from apps.common.money import money as as_money
from apps.common.money import zero
from apps.numbering.models import DocumentType
from apps.numbering.services import allocate
from apps.patients.models import Patient
from apps.radiology.models import (
    RadiologyConsumable,
    RadiologyConsumableMovement,
    RadiologyDepartment,
    RadiologyOrder,
    RadiologyOrderItem,
    RadiologyReport,
    RadiologyReportTemplate,
    RadiologyTest,
    RadiologyTestConsumable,
    StudyStatus,
)

STATUS_FLOW = {
    StudyStatus.REGISTERED: {StudyStatus.SCHEDULED, StudyStatus.IN_PROGRESS, StudyStatus.CANCELLED},
    StudyStatus.SCHEDULED: {StudyStatus.IN_PROGRESS, StudyStatus.CANCELLED},
    StudyStatus.IN_PROGRESS: {StudyStatus.COMPLETED, StudyStatus.CANCELLED},
    StudyStatus.COMPLETED: {StudyStatus.REPORTED, StudyStatus.CANCELLED},
    StudyStatus.REPORTED: {StudyStatus.AUTHORIZED, StudyStatus.CANCELLED},
    StudyStatus.AUTHORIZED: {StudyStatus.DISPATCHED},
    StudyStatus.DISPATCHED: set(),
    StudyStatus.CANCELLED: set(),
}


def _dec(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise AppError("Invalid numeric value.", code="invalid") from exc


def _patient(facility, patient_id) -> Patient:
    if not patient_id or not str(patient_id).strip():
        raise AppError("Patient is required.", code="invalid")
    try:
        return Patient.objects.get(id=str(patient_id).strip(), organization=facility.organization)
    except (Patient.DoesNotExist, ValidationError, ValueError) as exc:
        raise AppError(
            "Patient not found. Use the patient search or paste a valid patient id.",
            code="not_found",
        ) from exc


def _test(facility, test_id) -> RadiologyTest:
    try:
        return RadiologyTest.objects.get(id=test_id, facility=facility, is_active=True)
    except (RadiologyTest.DoesNotExist, ValidationError, ValueError) as exc:
        raise AppError("Radiology test not found.", code="not_found") from exc


def _order(facility, order_id) -> RadiologyOrder:
    try:
        return RadiologyOrder.objects.select_related("patient", "bill", "doctor").get(
            id=order_id, facility=facility
        )
    except (RadiologyOrder.DoesNotExist, ValidationError, ValueError) as exc:
        raise AppError("Radiology order not found.", code="not_found") from exc


def _item(facility, item_id) -> RadiologyOrderItem:
    try:
        return RadiologyOrderItem.objects.select_related("order", "test", "order__patient").get(
            id=item_id, order__facility=facility
        )
    except (RadiologyOrderItem.DoesNotExist, ValidationError, ValueError) as exc:
        raise AppError("Radiology order item not found.", code="not_found") from exc


def _assert_transition(item: RadiologyOrderItem, target: str) -> None:
    allowed = STATUS_FLOW.get(item.status, set())
    if target not in allowed:
        raise AppError(f"Cannot move from {item.status} to {target}.", code="invalid_status")


def _shares(test: RadiologyTest, price: Decimal) -> tuple[Decimal, Decimal]:
    hospital = as_money(test.hospital_share)
    doctor = as_money(test.doctor_share)
    if hospital + doctor == zero():
        return price, zero()
    total = hospital + doctor
    if total != price:
        # Scale shares to the billed price when masters diverge.
        hospital = as_money(price * hospital / total) if total else price
        doctor = as_money(price - hospital)
    return hospital, doctor


def test_payload(test: RadiologyTest) -> dict:
    return {
        "id": str(test.id),
        "code": test.code,
        "name": test.name,
        "description": test.description,
        "instruction": test.instruction,
        "department": test.department,
        "price": str(test.price),
        "hospital_share": str(test.hospital_share),
        "doctor_share": str(test.doctor_share),
        "tax_rate": str(test.tax_rate),
        "duration_minutes": test.duration_minutes,
        "is_active": test.is_active,
        "consumables": [
            {
                "id": str(link.id),
                "consumable_id": str(link.consumable_id),
                "consumable": link.consumable.name,
                "quantity_per_study": str(link.quantity_per_study),
            }
            for link in test.consumable_links.select_related("consumable")
        ],
    }


def template_payload(row: RadiologyReportTemplate) -> dict:
    return {
        "id": str(row.id),
        "code": row.code,
        "name": row.name,
        "department": row.department,
        "test_id": str(row.test_id) if row.test_id else "",
        "findings_template": row.findings_template,
        "impression_template": row.impression_template,
        "is_active": row.is_active,
    }


def report_payload(row: RadiologyReport) -> dict:
    return {
        "id": str(row.id),
        "findings": row.findings,
        "impression": row.impression,
        "template_id": str(row.template_id) if row.template_id else "",
        "version": row.version,
        "is_current": row.is_current,
        "amendment_reason": row.amendment_reason,
        "reported_by": row.reported_by.get_username(),
        "at": row.created_at.isoformat(),
    }


def item_payload(item: RadiologyOrderItem, *, include_report: bool = True) -> dict:
    data = {
        "id": str(item.id),
        "test_id": str(item.test_id),
        "test_code": item.test.code,
        "test_name": item.test.name,
        "department": item.test.department,
        "status": item.status,
        "unit_price": str(item.unit_price),
        "scheduled_at": item.scheduled_at.isoformat() if item.scheduled_at else None,
        "slot_label": item.slot_label,
        "performed_at": item.performed_at.isoformat() if item.performed_at else None,
        "reported_at": item.reported_at.isoformat() if item.reported_at else None,
        "authorized_at": item.authorized_at.isoformat() if item.authorized_at else None,
        "dispatched_at": item.dispatched_at.isoformat() if item.dispatched_at else None,
        "cancel_reason": item.cancel_reason,
        "pacs_url": item.pacs_url,
        "instruction": item.test.instruction,
    }
    if include_report:
        current = (
            item.reports.filter(is_current=True).select_related("reported_by", "template").first()
        )
        data["report"] = report_payload(current) if current else None
        data["templates"] = [
            template_payload(t)
            for t in RadiologyReportTemplate.objects.filter(
                facility=item.order.facility, is_active=True
            ).filter(Q(test=item.test) | Q(test__isnull=True, department=item.test.department) | Q(test__isnull=True, department=""))
        ]
    return data


def order_payload(order: RadiologyOrder, *, include_report: bool = True) -> dict:
    return {
        "id": str(order.id),
        "rad_no": order.rad_no,
        "patient_id": str(order.patient_id),
        "patient_name": order.patient.full_name,
        "uhid": order.patient.uhid,
        "visit_id": str(order.visit_id) if order.visit_id else "",
        "clinical_order_id": str(order.clinical_order_id) if order.clinical_order_id else "",
        "doctor_id": str(order.doctor_id) if order.doctor_id else "",
        "remarks": order.remarks,
        "bill": bill_payload(order.bill) if order.bill_id else None,
        "created_at": order.created_at.isoformat(),
        "items": [
            item_payload(i, include_report=include_report)
            for i in order.items.select_related("test").prefetch_related(
                Prefetch(
                    "reports",
                    queryset=RadiologyReport.objects.filter(is_current=True).select_related(
                        "reported_by", "template"
                    ),
                )
            )
        ],
    }


def list_tests(facility) -> list[dict]:
    return [
        test_payload(t)
        for t in RadiologyTest.objects.filter(facility=facility, is_active=True).prefetch_related(
            "consumable_links__consumable"
        )
    ]


def list_templates(facility) -> list[dict]:
    return [
        template_payload(t)
        for t in RadiologyReportTemplate.objects.filter(facility=facility, is_active=True)
    ]


def list_consumables(facility) -> list[dict]:
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "unit": r.unit,
            "quantity_on_hand": str(r.quantity_on_hand),
            "reorder_level": str(r.reorder_level),
            "below_reorder": r.quantity_on_hand < r.reorder_level,
        }
        for r in RadiologyConsumable.objects.filter(facility=facility, is_active=True)
    ]


@transaction.atomic
def create_test(*, actor, facility, data, request=None) -> dict:
    require_permission(actor, facility, "radiology.write")
    code = (data.get("code") or "").strip().upper()
    name = (data.get("name") or "").strip()
    department = data.get("department") or ""
    if not code or not name:
        raise AppError("Test code and name are required.", code="invalid")
    if department not in RadiologyDepartment.values:
        raise AppError("Unknown department.", code="invalid")
    price = as_money(data.get("price") or 0)
    hospital = as_money(data.get("hospital_share") if data.get("hospital_share") is not None else price)
    doctor = as_money(data.get("doctor_share") or 0)
    if hospital + doctor != price:
        raise AppError("Hospital and doctor shares must equal price.", code="bad_share")
    if RadiologyTest.objects.filter(facility=facility, code=code).exists():
        raise AppError("Test code already exists.", code="conflict")
    test = RadiologyTest.objects.create(
        facility=facility,
        code=code,
        name=name,
        description=(data.get("description") or "").strip(),
        instruction=(data.get("instruction") or "").strip(),
        department=department,
        price=price,
        hospital_share=hospital,
        doctor_share=doctor,
        tax_rate=as_money(data.get("tax_rate") or 0),
        duration_minutes=int(data.get("duration_minutes") or 30),
    )
    record_audit(
        action="radiology.test.create",
        actor=actor,
        facility=facility,
        entity_type="RadiologyTest",
        entity_id=str(test.id),
        after={"code": code},
        request=request,
    )
    return test_payload(test)


@transaction.atomic
def create_template(*, actor, facility, data, request=None) -> dict:
    require_permission(actor, facility, "radiology.write")
    code = (data.get("code") or "").strip().upper()
    name = (data.get("name") or "").strip()
    if not code or not name:
        raise AppError("Template code and name are required.", code="invalid")
    test = None
    if data.get("test_id"):
        test = _test(facility, data["test_id"])
    row = RadiologyReportTemplate.objects.create(
        facility=facility,
        code=code,
        name=name,
        department=(data.get("department") or (test.department if test else "")).strip(),
        test=test,
        findings_template=data.get("findings_template") or "",
        impression_template=data.get("impression_template") or "",
    )
    record_audit(
        action="radiology.template.create",
        actor=actor,
        facility=facility,
        entity_type="RadiologyReportTemplate",
        entity_id=str(row.id),
        after={"code": code},
        request=request,
    )
    return template_payload(row)


@transaction.atomic
def create_consumable(*, actor, facility, data, request=None) -> dict:
    require_permission(actor, facility, "radiology.write")
    name = (data.get("name") or "").strip()
    if not name:
        raise AppError("Consumable name is required.", code="invalid")
    RadiologyConsumable.objects.create(
        facility=facility,
        name=name,
        unit=(data.get("unit") or "UNIT").strip(),
        quantity_on_hand=_dec(data.get("quantity_on_hand") or 0) or Decimal("0"),
        reorder_level=_dec(data.get("reorder_level") or 0) or Decimal("0"),
    )
    record_audit(
        action="radiology.consumable.create",
        actor=actor,
        facility=facility,
        entity_type="RadiologyConsumable",
        entity_id=name,
        after={"name": name},
        request=request,
    )
    return list_consumables(facility)


@transaction.atomic
def link_consumable(*, actor, facility, test_id, data, request=None) -> dict:
    require_permission(actor, facility, "radiology.write")
    test = _test(facility, test_id)
    try:
        consumable = RadiologyConsumable.objects.get(
            id=data.get("consumable_id"), facility=facility, is_active=True
        )
    except (RadiologyConsumable.DoesNotExist, ValidationError, ValueError) as exc:
        raise AppError("Consumable not found.", code="not_found") from exc
    qty = _dec(data.get("quantity_per_study") or 1) or Decimal("1")
    RadiologyTestConsumable.objects.update_or_create(
        test=test, consumable=consumable, defaults={"quantity_per_study": qty}
    )
    return test_payload(test)


def _sync_clinical_order(order: RadiologyOrder) -> None:
    if not order.clinical_order_id:
        return
    co = order.clinical_order
    statuses = list(order.items.values_list("status", flat=True))
    if not statuses:
        return
    if all(s == StudyStatus.CANCELLED for s in statuses):
        new = "CANCELLED"
    elif all(s in (StudyStatus.DISPATCHED, StudyStatus.CANCELLED) for s in statuses):
        new = "COMPLETED"
    elif all(s == StudyStatus.REGISTERED for s in statuses):
        new = "ORDERED"
    else:
        new = "IN_PROGRESS"
    if new in ClinicalOrder.Status.values and co.status != new:
        co.status = new
        co.save(update_fields=["status", "updated_at"])


@transaction.atomic
def register_order(*, actor, facility, data, request=None) -> dict:
    require_permission(actor, facility, "radiology.register")
    test_ids = list(data.get("test_ids") or [])
    clinical_order = None
    if data.get("clinical_order_id"):
        try:
            clinical_order = ClinicalOrder.objects.select_related("visit", "doctor", "patient").get(
                id=data["clinical_order_id"], facility=facility, kind=ClinicalOrder.Kind.RADIOLOGY
            )
        except ClinicalOrder.DoesNotExist as exc:
            raise AppError("Clinical radiology order not found.", code="not_found") from exc
        patient = clinical_order.patient
        if clinical_order.code and not test_ids:
            match = RadiologyTest.objects.filter(
                facility=facility, code__iexact=clinical_order.code, is_active=True
            ).first()
            if match:
                test_ids = [str(match.id)]
            else:
                match = RadiologyTest.objects.filter(
                    facility=facility, name__iexact=clinical_order.name, is_active=True
                ).first()
                if match:
                    test_ids = [str(match.id)]
    elif data.get("patient_id"):
        patient = _patient(facility, data.get("patient_id"))
    else:
        raise AppError("Patient or clinical order is required.", code="invalid")
    if not test_ids:
        raise AppError("Select at least one test.", code="invalid")

    idempotency_key = (data.get("idempotency_key") or "").strip()
    if idempotency_key:
        existing = RadiologyOrder.objects.filter(
            facility=facility, idempotency_key=idempotency_key
        ).first()
        if existing:
            return order_payload(existing)

    visit = clinical_order.visit if clinical_order else None
    if data.get("visit_id") and not visit:
        from apps.opd.models import Visit

        try:
            visit = Visit.objects.select_related("doctor").get(
                id=data["visit_id"], facility=facility, patient=patient
            )
        except Visit.DoesNotExist as exc:
            raise AppError("Visit not found.", code="not_found") from exc

    doctor = None
    if clinical_order and clinical_order.doctor_id:
        doctor = clinical_order.doctor
    elif visit and visit.doctor_id:
        doctor = visit.doctor
    elif data.get("doctor_id"):
        from apps.masters.models import Doctor

        try:
            doctor = Doctor.objects.get(id=data["doctor_id"], facility=facility)
        except Doctor.DoesNotExist as exc:
            raise AppError("Doctor not found.", code="not_found") from exc

    rad_no = allocate(document_type=DocumentType.RAD, facility=facility, on_date=facility_today(facility))
    order = RadiologyOrder.objects.create(
        facility=facility,
        rad_no=rad_no,
        patient=patient,
        visit=visit,
        clinical_order=clinical_order,
        doctor=doctor,
        registered_by=actor,
        remarks=(data.get("remarks") or "").strip(),
        idempotency_key=idempotency_key,
    )

    charge_lines: list[ChargeLine] = []
    for tid in test_ids:
        test = _test(facility, tid)
        price = as_money(test.price)
        hospital, doctor_amt = _shares(test, price)
        item = RadiologyOrderItem.objects.create(
            order=order,
            test=test,
            unit_price=price,
            hospital_share=hospital,
            doctor_share=doctor_amt,
            status=StudyStatus.REGISTERED,
            pacs_url=(data.get("pacs_url") or "").strip(),
        )
        tax_rate = as_money(test.tax_rate)
        if not facility.settings.gstin_confirmed:
            tax_rate = zero()
        charge_lines.append(
            ChargeLine(
                source_type="radiology",
                source_id=f"{rad_no}:{item.id}",
                description=f"Radiology: {test.name}",
                amount=price,
                hospital_share=hospital,
                doctor_share=doctor_amt,
                tax_rate=tax_rate,
            )
        )

    bill = post_bill(
        facility=facility,
        patient=patient,
        actor=actor,
        lines=charge_lines,
        discount_type=data.get("discount_type") or DiscountType.NONE,
        discount_value=data.get("discount_value") or 0,
        paid=data.get("paid_amount"),
        payment_mode=data.get("payment_mode") or PaymentMode.CASH,
        idempotency_key=f"rad:{rad_no}",
    )
    order.bill = bill
    order.save(update_fields=["bill", "updated_at"])
    _sync_clinical_order(order)
    record_audit(
        action="radiology.order.register",
        actor=actor,
        facility=facility,
        entity_type="RadiologyOrder",
        entity_id=str(order.id),
        after={"rad_no": rad_no, "items": len(test_ids)},
        request=request,
    )
    return order_payload(order)


def list_orders(facility, *, status: str = "", department: str = "", q: str = "") -> list[dict]:
    qs = RadiologyOrder.objects.filter(facility=facility).select_related("patient", "bill")
    if q:
        qs = qs.filter(
            Q(rad_no__icontains=q)
            | Q(patient__uhid__icontains=q)
            | Q(patient__full_name__icontains=q)
            | Q(patient__mobile__icontains=q)
        )
    if status or department:
        item_filter = Q()
        if status:
            item_filter &= Q(items__status=status)
        if department:
            item_filter &= Q(items__test__department=department)
        qs = qs.filter(item_filter).distinct()
    return [order_payload(o, include_report=False) for o in qs.prefetch_related("items__test")[:100]]


def worklist(facility, *, department: str = "", status: str = "") -> list[dict]:
    qs = RadiologyOrderItem.objects.filter(order__facility=facility).select_related(
        "order", "order__patient", "test"
    )
    if department:
        qs = qs.filter(test__department=department)
    if status:
        qs = qs.filter(status=status)
    else:
        qs = qs.exclude(status__in=[StudyStatus.DISPATCHED, StudyStatus.CANCELLED])
    return [
        {
            **item_payload(item, include_report=False),
            "rad_no": item.order.rad_no,
            "order_id": str(item.order_id),
            "patient_name": item.order.patient.full_name,
            "uhid": item.order.patient.uhid,
        }
        for item in qs.order_by("scheduled_at", "created_at")[:200]
    ]


def schedule_board(facility, *, on_date: str = "") -> list[dict]:
    qs = RadiologyOrderItem.objects.filter(
        order__facility=facility, scheduled_at__isnull=False
    ).exclude(status=StudyStatus.CANCELLED).select_related("order", "order__patient", "test")
    if on_date:
        qs = qs.filter(scheduled_at__date=on_date)
    else:
        today = facility_today(facility)
        qs = qs.filter(scheduled_at__date=today)
    return [
        {
            **item_payload(item, include_report=False),
            "rad_no": item.order.rad_no,
            "order_id": str(item.order_id),
            "patient_name": item.order.patient.full_name,
            "uhid": item.order.patient.uhid,
        }
        for item in qs.order_by("scheduled_at")
    ]


def get_order(facility, order_id) -> dict:
    return order_payload(_order(facility, order_id))


@transaction.atomic
def schedule_item(*, actor, facility, item_id, data, request=None) -> dict:
    require_permission(actor, facility, "radiology.schedule")
    item = _item(facility, item_id)
    if item.status == StudyStatus.REGISTERED:
        _assert_transition(item, StudyStatus.SCHEDULED)
    elif item.status != StudyStatus.SCHEDULED:
        raise AppError("Only registered or scheduled items can be (re)scheduled.", code="invalid_status")
    when = data.get("scheduled_at")
    if not when:
        raise AppError("scheduled_at is required.", code="invalid")
    if hasattr(when, "isoformat"):
        dt = when
    else:
        dt = parse_datetime(str(when))
    if not dt:
        raise AppError("Invalid scheduled_at.", code="invalid")
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    item.scheduled_at = dt
    item.slot_label = (data.get("slot_label") or "").strip()
    item.status = StudyStatus.SCHEDULED
    item.save()
    _sync_clinical_order(item.order)
    record_audit(
        action="radiology.item.schedule",
        actor=actor,
        facility=facility,
        entity_type="RadiologyOrderItem",
        entity_id=str(item.id),
        after={"scheduled_at": item.scheduled_at.isoformat(), "slot": item.slot_label},
        request=request,
    )
    return item_payload(item)


def _consume(*, facility, item: RadiologyOrderItem, actor) -> None:
    for link in item.test.consumable_links.select_related("consumable"):
        consumable = RadiologyConsumable.objects.select_for_update().get(id=link.consumable_id)
        qty = link.quantity_per_study
        if consumable.quantity_on_hand < qty:
            raise AppError(
                f"Insufficient consumable stock for {consumable.name}.",
                code="insufficient_consumable",
            )
        consumable.quantity_on_hand = consumable.quantity_on_hand - qty
        consumable.save(update_fields=["quantity_on_hand", "updated_at"])
        RadiologyConsumableMovement.objects.create(
            facility=facility,
            consumable=consumable,
            kind=RadiologyConsumableMovement.Kind.CONSUME,
            delta=-qty,
            quantity_after=consumable.quantity_on_hand,
            actor=actor,
            order_item=item,
            remarks=f"Consumed for {item.order.rad_no}",
        )


@transaction.atomic
def start_study(*, actor, facility, item_id, request=None) -> dict:
    require_permission(actor, facility, "radiology.schedule")
    item = _item(facility, item_id)
    _assert_transition(item, StudyStatus.IN_PROGRESS)
    item.status = StudyStatus.IN_PROGRESS
    item.performed_by = actor
    item.save()
    _sync_clinical_order(item.order)
    record_audit(
        action="radiology.item.start",
        actor=actor,
        facility=facility,
        entity_type="RadiologyOrderItem",
        entity_id=str(item.id),
        request=request,
    )
    return item_payload(item)


@transaction.atomic
def complete_study(*, actor, facility, item_id, data=None, request=None) -> dict:
    require_permission(actor, facility, "radiology.schedule")
    item = _item(facility, item_id)
    data = data or {}
    if item.status in (StudyStatus.REGISTERED, StudyStatus.SCHEDULED):
        _assert_transition(item, StudyStatus.IN_PROGRESS)
        item.status = StudyStatus.IN_PROGRESS
        item.performed_by = actor
        item.save(update_fields=["status", "performed_by", "updated_at"])
        item = _item(facility, item_id)
    _assert_transition(item, StudyStatus.COMPLETED)
    if data.get("pacs_url"):
        item.pacs_url = str(data["pacs_url"]).strip()
    first_complete = item.performed_at is None
    item.status = StudyStatus.COMPLETED
    item.performed_at = timezone.now()
    item.performed_by = actor
    item.save()
    if first_complete:
        _consume(facility=facility, item=item, actor=actor)
    _sync_clinical_order(item.order)
    record_audit(
        action="radiology.item.complete",
        actor=actor,
        facility=facility,
        entity_type="RadiologyOrderItem",
        entity_id=str(item.id),
        request=request,
    )
    return item_payload(item)


@transaction.atomic
def save_report(*, actor, facility, item_id, data, request=None) -> dict:
    require_permission(actor, facility, "radiology.report")
    item = _item(facility, item_id)
    if item.status not in (
        StudyStatus.COMPLETED,
        StudyStatus.REPORTED,
        StudyStatus.AUTHORIZED,
        StudyStatus.DISPATCHED,
    ):
        raise AppError("Complete the study before reporting.", code="invalid_status")
    findings = (data.get("findings") or "").strip()
    impression = (data.get("impression") or "").strip()
    if not findings and not impression:
        raise AppError("Findings or impression is required.", code="invalid")
    template = None
    if data.get("template_id"):
        try:
            template = RadiologyReportTemplate.objects.get(
                id=data["template_id"], facility=facility, is_active=True
            )
        except RadiologyReportTemplate.DoesNotExist as exc:
            raise AppError("Template not found.", code="not_found") from exc
        if not findings and template.findings_template:
            findings = template.findings_template
        if not impression and template.impression_template:
            impression = template.impression_template

    existing = item.reports.filter(is_current=True).first()
    version = 1
    if existing:
        existing.is_current = False
        existing.save(update_fields=["is_current", "updated_at"])
        version = existing.version + 1
    RadiologyReport.objects.create(
        item=item,
        template=template,
        findings=findings,
        impression=impression,
        reported_by=actor,
        is_current=True,
        version=version,
        amended_from=existing,
        amendment_reason=(data.get("amendment_reason") or "").strip(),
    )
    if item.status in (StudyStatus.AUTHORIZED, StudyStatus.DISPATCHED):
        item.status = StudyStatus.REPORTED
        item.authorized_at = None
        item.authorized_by = None
        item.dispatched_at = None
    else:
        item.status = StudyStatus.REPORTED
    item.reported_at = timezone.now()
    item.save()
    _sync_clinical_order(item.order)
    record_audit(
        action="radiology.report.save",
        actor=actor,
        facility=facility,
        entity_type="RadiologyOrderItem",
        entity_id=str(item.id),
        after={"version": version},
        request=request,
    )
    return item_payload(item)


@transaction.atomic
def authorize_item(*, actor, facility, item_id, request=None) -> dict:
    require_permission(actor, facility, "radiology.authorize")
    item = _item(facility, item_id)
    _assert_transition(item, StudyStatus.AUTHORIZED)
    if not item.reports.filter(is_current=True).exists():
        raise AppError("Save a report before authorization.", code="invalid")
    item.status = StudyStatus.AUTHORIZED
    item.authorized_at = timezone.now()
    item.authorized_by = actor
    item.save()
    _sync_clinical_order(item.order)
    record_audit(
        action="radiology.report.authorize",
        actor=actor,
        facility=facility,
        entity_type="RadiologyOrderItem",
        entity_id=str(item.id),
        request=request,
    )
    return item_payload(item)


@transaction.atomic
def dispatch_item(*, actor, facility, item_id, request=None) -> dict:
    require_permission(actor, facility, "radiology.authorize")
    item = _item(facility, item_id)
    _assert_transition(item, StudyStatus.DISPATCHED)
    item.status = StudyStatus.DISPATCHED
    item.dispatched_at = timezone.now()
    item.save()
    _sync_clinical_order(item.order)
    record_audit(
        action="radiology.report.dispatch",
        actor=actor,
        facility=facility,
        entity_type="RadiologyOrderItem",
        entity_id=str(item.id),
        request=request,
    )
    return item_payload(item)


@transaction.atomic
def cancel_item(*, actor, facility, item_id, data, request=None) -> dict:
    require_permission(actor, facility, "radiology.register")
    item = _item(facility, item_id)
    if item.status in (StudyStatus.AUTHORIZED, StudyStatus.DISPATCHED):
        raise AppError("Cannot cancel after authorization.", code="invalid_status")
    if item.status == StudyStatus.CANCELLED:
        return item_payload(item)
    reason = (data.get("reason") or "").strip()
    if not reason:
        raise AppError("Cancel reason is required.", code="invalid")
    item.status = StudyStatus.CANCELLED
    item.cancelled_at = timezone.now()
    item.cancel_reason = reason
    item.save()
    _sync_clinical_order(item.order)
    record_audit(
        action="radiology.item.cancel",
        actor=actor,
        facility=facility,
        entity_type="RadiologyOrderItem",
        entity_id=str(item.id),
        after={"reason": reason},
        request=request,
    )
    return item_payload(item)


@transaction.atomic
def adjust_consumable(*, actor, facility, data, request=None) -> dict:
    require_permission(actor, facility, "radiology.adjust")
    try:
        consumable = RadiologyConsumable.objects.select_for_update().get(
            id=data.get("consumable_id"), facility=facility
        )
    except (RadiologyConsumable.DoesNotExist, ValidationError, ValueError) as exc:
        raise AppError("Consumable not found.", code="not_found") from exc
    kind = data.get("kind") or RadiologyConsumableMovement.Kind.ADJUST
    if kind not in RadiologyConsumableMovement.Kind.values:
        raise AppError("Unknown adjust kind.", code="invalid")
    delta = _dec(data.get("delta"))
    if delta is None or delta == 0:
        raise AppError("Delta is required.", code="invalid")
    if kind == RadiologyConsumableMovement.Kind.BREAKAGE and delta > 0:
        delta = -abs(delta)
    if kind == RadiologyConsumableMovement.Kind.RECEIVE and delta < 0:
        delta = abs(delta)
    new_qty = consumable.quantity_on_hand + delta
    if new_qty < 0:
        raise AppError("Insufficient consumable stock.", code="insufficient_consumable")
    consumable.quantity_on_hand = new_qty
    consumable.save(update_fields=["quantity_on_hand", "updated_at"])
    RadiologyConsumableMovement.objects.create(
        facility=facility,
        consumable=consumable,
        kind=kind,
        delta=delta,
        quantity_after=new_qty,
        actor=actor,
        remarks=(data.get("remarks") or "").strip(),
    )
    record_audit(
        action="radiology.consumable.adjust",
        actor=actor,
        facility=facility,
        entity_type="RadiologyConsumable",
        entity_id=str(consumable.id),
        after={"kind": kind, "delta": str(delta)},
        request=request,
    )
    return list_consumables(facility)
