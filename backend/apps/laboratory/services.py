"""Laboratory LIS: test master, sample lifecycle, results, reagents, reports."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone

from apps.accounts.permissions import require_permission
from apps.audit.services import record_audit
from apps.billing.models import DiscountType, PaymentMode
from apps.billing.services import ChargeLine, bill_payload, facility_today, post_bill
from apps.clinical.models import ClinicalOrder
from apps.common.exceptions import AppError
from apps.common.money import money as as_money
from apps.common.money import zero
from apps.laboratory.models import (
    FieldType,
    GenderScope,
    LabDepartment,
    LabOrder,
    LabOrderItem,
    LabPackage,
    LabReagent,
    LabReagentMovement,
    LabReferenceRange,
    LabResult,
    LabTest,
    LabTestField,
    LabTestReagent,
    ResultFlag,
    SampleStatus,
)
from apps.numbering.models import DocumentType
from apps.numbering.services import allocate
from apps.patients.models import Patient

STATUS_FLOW = {
    SampleStatus.REGISTERED: {SampleStatus.COLLECTED, SampleStatus.CANCELLED},
    SampleStatus.COLLECTED: {SampleStatus.RECEIVED, SampleStatus.CANCELLED},
    SampleStatus.RECEIVED: {SampleStatus.RESULTED, SampleStatus.CANCELLED},
    SampleStatus.RESULTED: {SampleStatus.VERIFIED, SampleStatus.CANCELLED},
    SampleStatus.VERIFIED: {SampleStatus.AUTHORIZED, SampleStatus.CANCELLED},
    SampleStatus.AUTHORIZED: {SampleStatus.DISPATCHED},
    SampleStatus.DISPATCHED: set(),
    SampleStatus.CANCELLED: set(),
}


def _patient(facility, patient_id) -> Patient:
    if not patient_id or not str(patient_id).strip():
        raise AppError("Patient is required.", code="invalid")
    try:
        return Patient.objects.get(id=str(patient_id).strip(), organization=facility.organization)
    except (Patient.DoesNotExist, ValidationError, ValueError) as exc:
        raise AppError("Patient not found. Use the patient search or paste a valid patient id.", code="not_found") from exc


def _test(facility, test_id) -> LabTest:
    try:
        return LabTest.objects.get(id=test_id, facility=facility, is_active=True)
    except (LabTest.DoesNotExist, ValidationError, ValueError) as exc:
        raise AppError("Lab test not found.", code="not_found") from exc


def _package(facility, package_id) -> LabPackage:
    try:
        return LabPackage.objects.prefetch_related("tests").get(
            id=package_id, facility=facility, is_active=True
        )
    except (LabPackage.DoesNotExist, ValidationError, ValueError) as exc:
        raise AppError("Lab package not found.", code="not_found") from exc


def _order(facility, order_id) -> LabOrder:
    try:
        return LabOrder.objects.select_related("patient", "bill", "doctor").get(
            id=order_id, facility=facility
        )
    except (LabOrder.DoesNotExist, ValidationError, ValueError) as exc:
        raise AppError("Lab order not found.", code="not_found") from exc


def _item(facility, item_id) -> LabOrderItem:
    try:
        return LabOrderItem.objects.select_related("order", "test", "order__patient").get(
            id=item_id, order__facility=facility
        )
    except (LabOrderItem.DoesNotExist, ValidationError, ValueError) as exc:
        raise AppError("Lab order item not found.", code="not_found") from exc


def _dec(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise AppError("Invalid numeric value.", code="invalid") from exc


def _patient_age_days(patient: Patient, on: date | None = None) -> int:
    on = on or timezone.localdate()
    dob = getattr(patient, "date_of_birth", None)
    if dob:
        return max(0, (on - dob).days)
    years = int(getattr(patient, "age_years", 0) or 0)
    if years:
        return years * 365
    return 30 * 365  # adult fallback


def _patient_gender(patient: Patient) -> str:
    g = (getattr(patient, "gender", "") or "").upper()
    if g in ("M", "MALE"):
        return GenderScope.MALE
    if g in ("F", "FEMALE"):
        return GenderScope.FEMALE
    return GenderScope.ANY


def _match_range(field: LabTestField, patient: Patient) -> LabReferenceRange | None:
    age = _patient_age_days(patient)
    gender = _patient_gender(patient)
    ranges = list(field.ranges.all())
    for row in ranges:
        if row.age_min_days <= age <= row.age_max_days and row.gender in (gender, GenderScope.ANY):
            if row.gender == gender:
                return row
    for row in ranges:
        if row.age_min_days <= age <= row.age_max_days and row.gender == GenderScope.ANY:
            return row
    return None


def _flag_value(
    *,
    field: LabTestField,
    patient: Patient,
    value_text: str,
    value_numeric: Decimal | None,
    test: LabTest,
) -> tuple[str, str, bool, bool]:
    """Return flag, reference_text, is_critical, is_delta."""
    ref = _match_range(field, patient)
    reference_text = ""
    flag = ResultFlag.NORMAL
    critical = False
    if field.field_type == FieldType.SUB_HEADER:
        return ResultFlag.NORMAL, "", False, False
    if ref:
        parts = []
        if field.field_type == FieldType.QUANTITATIVE and ref.low is not None and ref.high is not None:
            parts.append(f"{ref.low} – {ref.high}")
            if field.unit:
                parts[-1] += f" {field.unit}"
        elif ref.qualitative_normal:
            parts.append(ref.qualitative_normal)
        reference_text = " ".join(parts)
        if field.field_type == FieldType.QUANTITATIVE and value_numeric is not None:
            if ref.critical_low is not None and value_numeric <= ref.critical_low:
                flag = ResultFlag.CRITICAL
                critical = True
            elif ref.critical_high is not None and value_numeric >= ref.critical_high:
                flag = ResultFlag.CRITICAL
                critical = True
            elif ref.low is not None and value_numeric < ref.low:
                flag = ResultFlag.LOW
            elif ref.high is not None and value_numeric > ref.high:
                flag = ResultFlag.HIGH
        elif field.field_type == FieldType.QUALITATIVE and ref.qualitative_normal:
            if value_text.strip().lower() != ref.qualitative_normal.strip().lower():
                flag = ResultFlag.ABNORMAL

    is_delta = False
    if field.field_type == FieldType.QUANTITATIVE and value_numeric is not None:
        prev = (
            LabResult.objects.filter(
                field=field,
                is_current=True,
                item__order__patient=patient,
                item__status__in=[
                    SampleStatus.AUTHORIZED,
                    SampleStatus.DISPATCHED,
                    SampleStatus.VERIFIED,
                    SampleStatus.RESULTED,
                ],
                value_numeric__isnull=False,
            )
            .exclude(item__status=SampleStatus.CANCELLED)
            .order_by("-created_at")
            .first()
        )
        if prev and prev.value_numeric is not None:
            delta = abs(value_numeric - prev.value_numeric)
            abs_thr = test.delta_absolute
            pct_thr = test.delta_percent
            hit = False
            if abs_thr is not None and delta >= abs_thr:
                hit = True
            if pct_thr is not None and prev.value_numeric != 0:
                pct = (delta / abs(prev.value_numeric)) * Decimal("100")
                if pct >= pct_thr:
                    hit = True
            if hit:
                is_delta = True
                if flag == ResultFlag.NORMAL:
                    flag = ResultFlag.DELTA
    return flag, reference_text, critical, is_delta


def field_payload(field: LabTestField) -> dict:
    return {
        "id": str(field.id),
        "name": field.name,
        "field_type": field.field_type,
        "unit": field.unit,
        "sort_order": field.sort_order,
        "ranges": [
            {
                "id": str(r.id),
                "gender": r.gender,
                "age_min_days": r.age_min_days,
                "age_max_days": r.age_max_days,
                "low": str(r.low) if r.low is not None else None,
                "high": str(r.high) if r.high is not None else None,
                "critical_low": str(r.critical_low) if r.critical_low is not None else None,
                "critical_high": str(r.critical_high) if r.critical_high is not None else None,
                "qualitative_normal": r.qualitative_normal,
            }
            for r in field.ranges.all()
        ],
    }


def test_payload(test: LabTest) -> dict:
    return {
        "id": str(test.id),
        "code": test.code,
        "name": test.name,
        "department": test.department,
        "price": str(test.price),
        "tax_rate": str(test.tax_rate),
        "is_outsourced": test.is_outsourced,
        "outsource_lab": test.outsource_lab,
        "turnaround_hours": test.turnaround_hours,
        "delta_absolute": str(test.delta_absolute) if test.delta_absolute is not None else None,
        "delta_percent": str(test.delta_percent) if test.delta_percent is not None else None,
        "is_active": test.is_active,
        "fields": [field_payload(f) for f in test.fields.prefetch_related("ranges")],
        "reagents": [
            {
                "id": str(link.id),
                "reagent_id": str(link.reagent_id),
                "reagent": link.reagent.name,
                "quantity_per_test": str(link.quantity_per_test),
            }
            for link in test.reagent_links.select_related("reagent")
        ],
    }


def package_payload(pkg: LabPackage) -> dict:
    return {
        "id": str(pkg.id),
        "code": pkg.code,
        "name": pkg.name,
        "price": str(pkg.price),
        "is_active": pkg.is_active,
        "test_ids": [str(t.id) for t in pkg.tests.all()],
        "tests": [{"id": str(t.id), "code": t.code, "name": t.name} for t in pkg.tests.all()],
    }


def result_payload(row: LabResult) -> dict:
    return {
        "id": str(row.id),
        "field_id": str(row.field_id),
        "field": row.field.name,
        "field_type": row.field.field_type,
        "unit": row.field.unit,
        "value_text": row.value_text,
        "value_numeric": str(row.value_numeric) if row.value_numeric is not None else None,
        "flag": row.flag,
        "reference_text": row.reference_text,
        "version": row.version,
        "is_current": row.is_current,
        "amendment_reason": row.amendment_reason,
        "entered_by": row.entered_by.get_username(),
        "at": row.created_at.isoformat(),
    }


def item_payload(item: LabOrderItem, *, include_results: bool = True) -> dict:
    data = {
        "id": str(item.id),
        "test_id": str(item.test_id),
        "test_code": item.test.code,
        "test_name": item.test.name,
        "department": item.test.department,
        "status": item.status,
        "barcode": item.barcode,
        "unit_price": str(item.unit_price),
        "is_outsourced": item.is_outsourced,
        "outsource_lab": item.outsource_lab,
        "has_critical": item.has_critical,
        "has_delta": item.has_delta,
        "collected_at": item.collected_at.isoformat() if item.collected_at else None,
        "received_at": item.received_at.isoformat() if item.received_at else None,
        "resulted_at": item.resulted_at.isoformat() if item.resulted_at else None,
        "verified_at": item.verified_at.isoformat() if item.verified_at else None,
        "authorized_at": item.authorized_at.isoformat() if item.authorized_at else None,
        "dispatched_at": item.dispatched_at.isoformat() if item.dispatched_at else None,
        "cancel_reason": item.cancel_reason,
    }
    if include_results:
        data["results"] = [
            result_payload(r)
            for r in item.results.filter(is_current=True).select_related("field", "entered_by")
        ]
        data["fields"] = [field_payload(f) for f in item.test.fields.prefetch_related("ranges")]
    return data


def order_payload(order: LabOrder, *, include_results: bool = True) -> dict:
    return {
        "id": str(order.id),
        "lab_no": order.lab_no,
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
            item_payload(i, include_results=include_results)
            for i in order.items.select_related("test").prefetch_related(
                Prefetch(
                    "results",
                    queryset=LabResult.objects.filter(is_current=True).select_related(
                        "field", "entered_by"
                    ),
                ),
                "test__fields__ranges",
            )
        ],
    }


def list_tests(facility) -> list[dict]:
    return [
        test_payload(t)
        for t in LabTest.objects.filter(facility=facility, is_active=True).prefetch_related(
            "fields__ranges", "reagent_links__reagent"
        )
    ]


def list_packages(facility) -> list[dict]:
    return [
        package_payload(p)
        for p in LabPackage.objects.filter(facility=facility, is_active=True).prefetch_related("tests")
    ]


def list_reagents(facility) -> list[dict]:
    rows = []
    for r in LabReagent.objects.filter(facility=facility, is_active=True):
        rows.append(
            {
                "id": str(r.id),
                "name": r.name,
                "unit": r.unit,
                "quantity_on_hand": str(r.quantity_on_hand),
                "reorder_level": str(r.reorder_level),
                "below_reorder": r.quantity_on_hand < r.reorder_level,
            }
        )
    return rows


@transaction.atomic
def create_test(*, actor, facility, data, request=None) -> dict:
    require_permission(actor, facility, "laboratory.write")
    code = (data.get("code") or "").strip().upper()
    name = (data.get("name") or "").strip()
    department = data.get("department") or ""
    if not code or not name:
        raise AppError("Test code and name are required.", code="invalid")
    if department not in LabDepartment.values:
        raise AppError("Unknown department.", code="invalid")
    if LabTest.objects.filter(facility=facility, code=code).exists():
        raise AppError("Test code already exists.", code="conflict")
    test = LabTest.objects.create(
        facility=facility,
        code=code,
        name=name,
        department=department,
        price=as_money(data.get("price") or 0),
        tax_rate=as_money(data.get("tax_rate") or 0),
        is_outsourced=bool(data.get("is_outsourced")),
        outsource_lab=(data.get("outsource_lab") or "").strip(),
        turnaround_hours=int(data.get("turnaround_hours") or 24),
        delta_absolute=_dec(data.get("delta_absolute")),
        delta_percent=_dec(data.get("delta_percent")),
    )
    for idx, field in enumerate(data.get("fields") or []):
        _add_field(test, field, idx)
    record_audit(
        action="laboratory.test.create",
        actor=actor,
        facility=facility,
        entity_type="LabTest",
        entity_id=str(test.id),
        after={"code": code, "name": name},
        request=request,
    )
    return test_payload(test)


def _add_field(test: LabTest, field: dict, sort_fallback: int) -> LabTestField:
    fname = (field.get("name") or "").strip()
    ftype = field.get("field_type") or FieldType.QUANTITATIVE
    if not fname:
        raise AppError("Field name is required.", code="invalid")
    if ftype not in FieldType.values:
        raise AppError("Unknown field type.", code="invalid")
    row = LabTestField.objects.create(
        test=test,
        name=fname,
        field_type=ftype,
        unit=(field.get("unit") or "").strip(),
        sort_order=int(field.get("sort_order") if field.get("sort_order") is not None else sort_fallback),
    )
    for rng in field.get("ranges") or []:
        LabReferenceRange.objects.create(
            field=row,
            gender=rng.get("gender") or GenderScope.ANY,
            age_min_days=int(rng.get("age_min_days") or 0),
            age_max_days=int(rng.get("age_max_days") or 36500),
            low=_dec(rng.get("low")),
            high=_dec(rng.get("high")),
            critical_low=_dec(rng.get("critical_low")),
            critical_high=_dec(rng.get("critical_high")),
            qualitative_normal=(rng.get("qualitative_normal") or "").strip(),
        )
    return row


@transaction.atomic
def add_test_field(*, actor, facility, test_id, data, request=None) -> dict:
    require_permission(actor, facility, "laboratory.write")
    test = _test(facility, test_id)
    field = _add_field(test, data, test.fields.count())
    record_audit(
        action="laboratory.test.field.add",
        actor=actor,
        facility=facility,
        entity_type="LabTestField",
        entity_id=str(field.id),
        after={"test": test.code, "name": field.name},
        request=request,
    )
    return test_payload(test)


@transaction.atomic
def create_package(*, actor, facility, data, request=None) -> dict:
    require_permission(actor, facility, "laboratory.write")
    code = (data.get("code") or "").strip().upper()
    name = (data.get("name") or "").strip()
    if not code or not name:
        raise AppError("Package code and name are required.", code="invalid")
    pkg = LabPackage.objects.create(
        facility=facility,
        code=code,
        name=name,
        price=as_money(data.get("price") or 0),
    )
    tests = []
    for tid in data.get("test_ids") or []:
        tests.append(_test(facility, tid))
    if tests:
        pkg.tests.set(tests)
    record_audit(
        action="laboratory.package.create",
        actor=actor,
        facility=facility,
        entity_type="LabPackage",
        entity_id=str(pkg.id),
        after={"code": code},
        request=request,
    )
    return package_payload(pkg)


@transaction.atomic
def create_reagent(*, actor, facility, data, request=None) -> dict:
    require_permission(actor, facility, "laboratory.write")
    name = (data.get("name") or "").strip()
    if not name:
        raise AppError("Reagent name is required.", code="invalid")
    row = LabReagent.objects.create(
        facility=facility,
        name=name,
        unit=(data.get("unit") or "ML").strip(),
        quantity_on_hand=_dec(data.get("quantity_on_hand") or 0) or Decimal("0"),
        reorder_level=_dec(data.get("reorder_level") or 0) or Decimal("0"),
    )
    record_audit(
        action="laboratory.reagent.create",
        actor=actor,
        facility=facility,
        entity_type="LabReagent",
        entity_id=str(row.id),
        after={"name": name},
        request=request,
    )
    return list_reagents(facility)


@transaction.atomic
def link_reagent(*, actor, facility, test_id, data, request=None) -> dict:
    require_permission(actor, facility, "laboratory.write")
    test = _test(facility, test_id)
    try:
        reagent = LabReagent.objects.get(id=data.get("reagent_id"), facility=facility, is_active=True)
    except LabReagent.DoesNotExist as exc:
        raise AppError("Reagent not found.", code="not_found") from exc
    qty = _dec(data.get("quantity_per_test") or 1) or Decimal("1")
    LabTestReagent.objects.update_or_create(
        test=test, reagent=reagent, defaults={"quantity_per_test": qty}
    )
    record_audit(
        action="laboratory.test.reagent.link",
        actor=actor,
        facility=facility,
        entity_type="LabTest",
        entity_id=str(test.id),
        after={"reagent": reagent.name, "qty": str(qty)},
        request=request,
    )
    return test_payload(test)


def _sync_clinical_order(order: LabOrder) -> None:
    if not order.clinical_order_id:
        return
    co = order.clinical_order
    statuses = list(order.items.values_list("status", flat=True))
    if not statuses:
        return
    if all(s == SampleStatus.CANCELLED for s in statuses):
        new = "CANCELLED"
    elif all(s in (SampleStatus.DISPATCHED, SampleStatus.CANCELLED) for s in statuses):
        new = "COMPLETED"
    elif all(s == SampleStatus.REGISTERED for s in statuses):
        new = "ORDERED"
    else:
        new = "IN_PROGRESS"
    if hasattr(ClinicalOrder.Status, new) or new in ClinicalOrder.Status.values:
        if co.status != new:
            co.status = new
            co.save(update_fields=["status", "updated_at"])


@transaction.atomic
def register_order(*, actor, facility, data, request=None) -> dict:
    require_permission(actor, facility, "laboratory.register")
    test_ids = list(data.get("test_ids") or [])
    package_ids = list(data.get("package_ids") or [])
    clinical_order = None
    if data.get("clinical_order_id"):
        try:
            clinical_order = ClinicalOrder.objects.select_related("visit", "doctor", "patient").get(
                id=data["clinical_order_id"], facility=facility, kind=ClinicalOrder.Kind.LAB
            )
        except ClinicalOrder.DoesNotExist as exc:
            raise AppError("Clinical lab order not found.", code="not_found") from exc
        patient = clinical_order.patient
        if clinical_order.code and not test_ids and not package_ids:
            match = LabTest.objects.filter(
                facility=facility, code__iexact=clinical_order.code, is_active=True
            ).first()
            if match:
                test_ids = [str(match.id)]
            else:
                match = LabTest.objects.filter(
                    facility=facility, name__iexact=clinical_order.name, is_active=True
                ).first()
                if match:
                    test_ids = [str(match.id)]
    elif data.get("patient_id"):
        patient = _patient(facility, data.get("patient_id"))
    else:
        raise AppError("Patient or clinical order is required.", code="invalid")
    if not test_ids and not package_ids:
        raise AppError("Select at least one test or package.", code="invalid")

    idempotency_key = (data.get("idempotency_key") or "").strip()
    if idempotency_key:
        existing = LabOrder.objects.filter(facility=facility, idempotency_key=idempotency_key).first()
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

    lab_no = allocate(document_type=DocumentType.LAB, facility=facility, on_date=facility_today(facility))
    order = LabOrder.objects.create(
        facility=facility,
        lab_no=lab_no,
        patient=patient,
        visit=visit,
        clinical_order=clinical_order,
        doctor=doctor,
        registered_by=actor,
        remarks=(data.get("remarks") or "").strip(),
        idempotency_key=idempotency_key,
    )

    charge_lines: list[ChargeLine] = []
    line_index = 0
    expanded: list[tuple[LabTest, LabPackage | None, Decimal]] = []

    for pid in package_ids:
        pkg = _package(facility, pid)
        tests = list(pkg.tests.filter(is_active=True))
        if not tests:
            raise AppError(f"Package {pkg.code} has no tests.", code="invalid")
        share = as_money(pkg.price / len(tests)) if pkg.price else zero()
        remainder = as_money(pkg.price - share * len(tests)) if pkg.price else zero()
        for i, t in enumerate(tests):
            price = share + (remainder if i == 0 else zero())
            expanded.append((t, pkg, price if pkg.price else as_money(t.price)))

    for tid in test_ids:
        expanded.append((_test(facility, tid), None, None))

    for test, pkg, override_price in expanded:
        line_index += 1
        price = as_money(override_price if override_price is not None else test.price)
        barcode = f"{lab_no}-{line_index:02d}"
        item = LabOrderItem.objects.create(
            order=order,
            test=test,
            package=pkg,
            barcode=barcode,
            unit_price=price,
            is_outsourced=test.is_outsourced,
            outsource_lab=test.outsource_lab,
            status=SampleStatus.REGISTERED,
        )
        tax_rate = as_money(test.tax_rate)
        if not facility.settings.gstin_confirmed:
            tax_rate = zero()
        charge_lines.append(
            ChargeLine(
                source_type="laboratory",
                source_id=f"{lab_no}:{item.barcode}",
                description=f"Lab: {test.name}",
                amount=price,
                hospital_share=price,
                doctor_share=zero(),
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
        idempotency_key=f"lab:{lab_no}",
    )
    order.bill = bill
    order.save(update_fields=["bill", "updated_at"])
    _sync_clinical_order(order)
    record_audit(
        action="laboratory.order.register",
        actor=actor,
        facility=facility,
        entity_type="LabOrder",
        entity_id=str(order.id),
        after={"lab_no": lab_no, "items": line_index},
        request=request,
    )
    return order_payload(order)


def list_orders(facility, *, status: str = "", department: str = "", q: str = "") -> list[dict]:
    qs = LabOrder.objects.filter(facility=facility).select_related("patient", "bill")
    if q:
        qs = qs.filter(
            Q(lab_no__icontains=q)
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
    return [order_payload(o, include_results=False) for o in qs.prefetch_related("items__test")[:100]]


def worklist(facility, *, department: str = "", status: str = "") -> list[dict]:
    qs = LabOrderItem.objects.filter(order__facility=facility).select_related(
        "order", "order__patient", "test"
    )
    if department:
        qs = qs.filter(test__department=department)
    if status:
        qs = qs.filter(status=status)
    else:
        qs = qs.exclude(status__in=[SampleStatus.DISPATCHED, SampleStatus.CANCELLED])
    rows = []
    for item in qs.order_by("test__department", "created_at")[:200]:
        rows.append(
            {
                **item_payload(item, include_results=False),
                "lab_no": item.order.lab_no,
                "order_id": str(item.order_id),
                "patient_name": item.order.patient.full_name,
                "uhid": item.order.patient.uhid,
            }
        )
    return rows


def get_order(facility, order_id) -> dict:
    return order_payload(_order(facility, order_id))


@transaction.atomic
def collect_sample(*, actor, facility, item_id, data=None, request=None) -> dict:
    require_permission(actor, facility, "laboratory.collect")
    item = _item(facility, item_id)
    _assert_transition(item, SampleStatus.COLLECTED)
    data = data or {}
    if data.get("barcode"):
        item.barcode = str(data["barcode"]).strip()
    item.status = SampleStatus.COLLECTED
    item.collected_at = timezone.now()
    item.collected_by = actor
    item.save()
    _sync_clinical_order(item.order)
    record_audit(
        action="laboratory.sample.collect",
        actor=actor,
        facility=facility,
        entity_type="LabOrderItem",
        entity_id=str(item.id),
        after={"barcode": item.barcode, "status": item.status},
        request=request,
    )
    return item_payload(item)


@transaction.atomic
def receive_sample(*, actor, facility, item_id, request=None) -> dict:
    require_permission(actor, facility, "laboratory.collect")
    item = _item(facility, item_id)
    _assert_transition(item, SampleStatus.RECEIVED)
    item.status = SampleStatus.RECEIVED
    item.received_at = timezone.now()
    item.received_by = actor
    item.save()
    _sync_clinical_order(item.order)
    record_audit(
        action="laboratory.sample.receive",
        actor=actor,
        facility=facility,
        entity_type="LabOrderItem",
        entity_id=str(item.id),
        after={"status": item.status},
        request=request,
    )
    return item_payload(item)


def _assert_transition(item: LabOrderItem, target: str) -> None:
    allowed = STATUS_FLOW.get(item.status, set())
    if target not in allowed:
        raise AppError(
            f"Cannot move from {item.status} to {target}.",
            code="invalid_status",
        )


def _consume_reagents(*, facility, item: LabOrderItem, actor) -> None:
    for link in item.test.reagent_links.select_related("reagent"):
        reagent = LabReagent.objects.select_for_update().get(id=link.reagent_id)
        qty = link.quantity_per_test
        if reagent.quantity_on_hand < qty:
            raise AppError(
                f"Insufficient reagent stock for {reagent.name}.",
                code="insufficient_reagent",
            )
        reagent.quantity_on_hand = reagent.quantity_on_hand - qty
        reagent.save(update_fields=["quantity_on_hand", "updated_at"])
        LabReagentMovement.objects.create(
            facility=facility,
            reagent=reagent,
            kind=LabReagentMovement.Kind.CONSUME,
            delta=-qty,
            quantity_after=reagent.quantity_on_hand,
            actor=actor,
            order_item=item,
            remarks=f"Consumed for {item.barcode}",
        )


@transaction.atomic
def enter_results(*, actor, facility, item_id, data, request=None) -> dict:
    require_permission(actor, facility, "laboratory.result")
    item = _item(facility, item_id)
    if item.status == SampleStatus.RECEIVED:
        _assert_transition(item, SampleStatus.RESULTED)
    elif item.status == SampleStatus.RESULTED:
        pass  # allow overwrite before verify
    else:
        raise AppError("Results can only be entered after sample receipt.", code="invalid_status")

    values = data.get("results") or []
    if not values:
        raise AppError("Provide at least one result value.", code="invalid")

    fields = {str(f.id): f for f in item.test.fields.all()}
    critical = False
    delta = False
    first_entry = item.status == SampleStatus.RECEIVED

    for row in values:
        field = fields.get(str(row.get("field_id")))
        if not field:
            raise AppError("Unknown result field.", code="invalid")
        if field.field_type == FieldType.SUB_HEADER:
            continue
        value_text = (row.get("value_text") or "").strip()
        value_numeric = _dec(row.get("value_numeric"))
        if field.field_type == FieldType.QUANTITATIVE and value_numeric is None and value_text:
            value_numeric = _dec(value_text)
        if field.field_type == FieldType.QUANTITATIVE and value_numeric is None:
            raise AppError(f"Numeric value required for {field.name}.", code="invalid")
        if field.field_type != FieldType.QUANTITATIVE and not value_text:
            raise AppError(f"Value required for {field.name}.", code="invalid")
        if field.field_type == FieldType.QUANTITATIVE and not value_text:
            value_text = str(value_numeric)

        flag, reference_text, is_crit, is_delta = _flag_value(
            field=field,
            patient=item.order.patient,
            value_text=value_text,
            value_numeric=value_numeric,
            test=item.test,
        )
        critical = critical or is_crit
        delta = delta or is_delta

        existing = LabResult.objects.filter(item=item, field=field, is_current=True).first()
        version = 1
        if existing:
            existing.is_current = False
            existing.save(update_fields=["is_current", "updated_at"])
            version = existing.version + 1
        LabResult.objects.create(
            item=item,
            field=field,
            value_text=value_text,
            value_numeric=value_numeric,
            flag=flag,
            reference_text=reference_text,
            entered_by=actor,
            is_current=True,
            version=version,
            amended_from=existing,
        )

    if first_entry:
        _consume_reagents(facility=facility, item=item, actor=actor)

    item.status = SampleStatus.RESULTED
    item.resulted_at = timezone.now()
    item.has_critical = critical
    item.has_delta = delta
    item.save()
    _sync_clinical_order(item.order)
    record_audit(
        action="laboratory.result.enter",
        actor=actor,
        facility=facility,
        entity_type="LabOrderItem",
        entity_id=str(item.id),
        after={"critical": critical, "delta": delta},
        request=request,
    )
    return item_payload(item)


@transaction.atomic
def amend_results(*, actor, facility, item_id, data, request=None) -> dict:
    require_permission(actor, facility, "laboratory.authorize")
    item = _item(facility, item_id)
    if item.status not in (
        SampleStatus.AUTHORIZED,
        SampleStatus.DISPATCHED,
        SampleStatus.VERIFIED,
        SampleStatus.RESULTED,
    ):
        raise AppError("Nothing to amend yet.", code="invalid_status")
    reason = (data.get("reason") or "").strip()
    if not reason:
        raise AppError("Amendment reason is required.", code="invalid")
    # Drop to RESULTED so enter_results can overwrite without re-consuming reagents.
    item.status = SampleStatus.RESULTED
    item.verified_at = None
    item.verified_by = None
    item.authorized_at = None
    item.authorized_by = None
    item.dispatched_at = None
    item.save(
        update_fields=[
            "status",
            "verified_at",
            "verified_by",
            "authorized_at",
            "authorized_by",
            "dispatched_at",
            "updated_at",
        ]
    )
    enter_results(actor=actor, facility=facility, item_id=item_id, data=data, request=request)
    item = _item(facility, item_id)
    for r in item.results.filter(is_current=True):
        if not r.amendment_reason:
            r.amendment_reason = reason
            r.save(update_fields=["amendment_reason", "updated_at"])
    record_audit(
        action="laboratory.result.amend",
        actor=actor,
        facility=facility,
        entity_type="LabOrderItem",
        entity_id=str(item.id),
        after={"reason": reason},
        request=request,
    )
    return item_payload(item)


@transaction.atomic
def verify_item(*, actor, facility, item_id, request=None) -> dict:
    require_permission(actor, facility, "laboratory.result")
    item = _item(facility, item_id)
    _assert_transition(item, SampleStatus.VERIFIED)
    if not item.results.filter(is_current=True).exists():
        raise AppError("Enter results before verify.", code="invalid")
    item.status = SampleStatus.VERIFIED
    item.verified_at = timezone.now()
    item.verified_by = actor
    item.save()
    _sync_clinical_order(item.order)
    record_audit(
        action="laboratory.result.verify",
        actor=actor,
        facility=facility,
        entity_type="LabOrderItem",
        entity_id=str(item.id),
        request=request,
    )
    return item_payload(item)


@transaction.atomic
def authorize_item(*, actor, facility, item_id, request=None) -> dict:
    require_permission(actor, facility, "laboratory.authorize")
    item = _item(facility, item_id)
    _assert_transition(item, SampleStatus.AUTHORIZED)
    item.status = SampleStatus.AUTHORIZED
    item.authorized_at = timezone.now()
    item.authorized_by = actor
    item.save()
    _sync_clinical_order(item.order)
    record_audit(
        action="laboratory.result.authorize",
        actor=actor,
        facility=facility,
        entity_type="LabOrderItem",
        entity_id=str(item.id),
        request=request,
    )
    return item_payload(item)


@transaction.atomic
def dispatch_item(*, actor, facility, item_id, request=None) -> dict:
    require_permission(actor, facility, "laboratory.authorize")
    item = _item(facility, item_id)
    _assert_transition(item, SampleStatus.DISPATCHED)
    item.status = SampleStatus.DISPATCHED
    item.dispatched_at = timezone.now()
    item.save()
    _sync_clinical_order(item.order)
    record_audit(
        action="laboratory.report.dispatch",
        actor=actor,
        facility=facility,
        entity_type="LabOrderItem",
        entity_id=str(item.id),
        request=request,
    )
    return item_payload(item)


@transaction.atomic
def cancel_item(*, actor, facility, item_id, data, request=None) -> dict:
    require_permission(actor, facility, "laboratory.register")
    item = _item(facility, item_id)
    if item.status in (SampleStatus.AUTHORIZED, SampleStatus.DISPATCHED):
        raise AppError("Cannot cancel after authorization.", code="invalid_status")
    if item.status == SampleStatus.CANCELLED:
        return item_payload(item)
    reason = (data.get("reason") or "").strip()
    if not reason:
        raise AppError("Cancel reason is required.", code="invalid")
    item.status = SampleStatus.CANCELLED
    item.cancelled_at = timezone.now()
    item.cancel_reason = reason
    item.save()
    _sync_clinical_order(item.order)
    record_audit(
        action="laboratory.item.cancel",
        actor=actor,
        facility=facility,
        entity_type="LabOrderItem",
        entity_id=str(item.id),
        after={"reason": reason},
        request=request,
    )
    return item_payload(item)


@transaction.atomic
def adjust_reagent(*, actor, facility, data, request=None) -> dict:
    require_permission(actor, facility, "laboratory.adjust")
    try:
        reagent = LabReagent.objects.select_for_update().get(
            id=data.get("reagent_id"), facility=facility
        )
    except LabReagent.DoesNotExist as exc:
        raise AppError("Reagent not found.", code="not_found") from exc
    kind = data.get("kind") or LabReagentMovement.Kind.ADJUST
    if kind not in LabReagentMovement.Kind.values:
        raise AppError("Unknown adjust kind.", code="invalid")
    delta = _dec(data.get("delta"))
    if delta is None or delta == 0:
        raise AppError("Delta is required.", code="invalid")
    if kind == LabReagentMovement.Kind.BREAKAGE and delta > 0:
        delta = -abs(delta)
    if kind == LabReagentMovement.Kind.RECEIVE and delta < 0:
        delta = abs(delta)
    new_qty = reagent.quantity_on_hand + delta
    if new_qty < 0:
        raise AppError("Insufficient reagent stock.", code="insufficient_reagent")
    reagent.quantity_on_hand = new_qty
    reagent.save(update_fields=["quantity_on_hand", "updated_at"])
    LabReagentMovement.objects.create(
        facility=facility,
        reagent=reagent,
        kind=kind,
        delta=delta,
        quantity_after=new_qty,
        actor=actor,
        remarks=(data.get("remarks") or "").strip(),
    )
    record_audit(
        action="laboratory.reagent.adjust",
        actor=actor,
        facility=facility,
        entity_type="LabReagent",
        entity_id=str(reagent.id),
        after={"kind": kind, "delta": str(delta)},
        request=request,
    )
    return list_reagents(facility)


def critical_alerts(facility) -> list[dict]:
    qs = LabOrderItem.objects.filter(
        order__facility=facility,
        has_critical=True,
    ).exclude(status=SampleStatus.CANCELLED).select_related("order", "order__patient", "test")[:50]
    return [
        {
            "item_id": str(i.id),
            "lab_no": i.order.lab_no,
            "patient": i.order.patient.full_name,
            "test": i.test.name,
            "status": i.status,
            "barcode": i.barcode,
        }
        for i in qs
    ]


def barcode_label(*, actor, facility, item_id) -> dict:
    require_permission(actor, facility, "laboratory.read")
    item = _item(facility, item_id)
    return {
        "barcode": item.barcode,
        "lab_no": item.order.lab_no,
        "patient": item.order.patient.full_name,
        "uhid": item.order.patient.uhid,
        "test": item.test.name,
        "department": item.test.department,
        "collected_at": item.collected_at.isoformat() if item.collected_at else None,
    }
