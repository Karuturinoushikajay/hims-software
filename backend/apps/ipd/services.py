"""In-patient admissions, bed board, transfers, daily charges, nursing, discharge."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.accounts.permissions import require_permission
from apps.audit.services import record_audit
from apps.billing.models import Advance, Bill, PaymentMode
from apps.billing.services import ChargeLine, bill_payload, facility_today, post_bill
from apps.billing.settlement import apply_advance, take_advance
from apps.common.exceptions import AppError
from apps.common.money import money as as_money
from apps.common.money import zero
from apps.ipd.models import (
    AdmissionStatus,
    CertificateKind,
    FoodPreference,
    IpAdmission,
    IpDailyCharge,
    IpDischargeSummary,
    IpDoctorOrder,
    IpMedicationAdmin,
    IpNursingNote,
    IpTransfer,
    MedicalCertificate,
)
from apps.masters.models import Bed, Doctor, DocumentTemplate, Service
from apps.numbering.models import DocumentType
from apps.numbering.services import allocate
from apps.patients.models import Patient

DEFAULT_BED_RATES = {
    "ER Ward": Decimal("2000.00"),
    "General Ward": Decimal("1500.00"),
    "ICU": Decimal("5000.00"),
    "Step Down ICU": Decimal("3500.00"),
    "Special Rooms": Decimal("4000.00"),
}


def _dec(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise AppError("Invalid numeric value.", code="invalid") from exc


def _patient(facility, patient_id) -> Patient:
    if not patient_id:
        raise AppError("Patient is required.", code="invalid")
    try:
        return Patient.objects.get(id=str(patient_id).strip(), organization=facility.organization)
    except (Patient.DoesNotExist, ValidationError, ValueError) as exc:
        raise AppError("Patient not found.", code="not_found") from exc


def _doctor(facility, doctor_id) -> Doctor:
    try:
        return Doctor.objects.get(id=doctor_id, facility=facility, is_active=True)
    except (Doctor.DoesNotExist, ValidationError, ValueError) as exc:
        raise AppError("Doctor not found.", code="not_found") from exc


def _bed(facility, bed_id) -> Bed:
    try:
        return Bed.objects.select_related("room__ward__room_type", "room__ward").get(
            id=bed_id, room__ward__facility=facility, is_active=True
        )
    except (Bed.DoesNotExist, ValidationError, ValueError) as exc:
        raise AppError("Bed not found.", code="not_found") from exc


def _admission(facility, admission_id) -> IpAdmission:
    try:
        return IpAdmission.objects.select_related(
            "patient", "doctor", "secondary_doctor", "bed__room__ward__room_type", "settlement_bill"
        ).get(id=admission_id, facility=facility)
    except (IpAdmission.DoesNotExist, ValidationError, ValueError) as exc:
        raise AppError("Admission not found.", code="not_found") from exc


def _parse_dt(value, *, required=True):
    if value is None or value == "":
        if required:
            raise AppError("Date/time is required.", code="invalid")
        return None
    if hasattr(value, "isoformat") and not isinstance(value, str):
        dt = value
    else:
        dt = parse_datetime(str(value))
        if dt is None:
            d = parse_date(str(value))
            if d:
                dt = datetime.combine(d, datetime.min.time())
    if not dt:
        raise AppError("Invalid date/time.", code="invalid")
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _default_bed_rate(bed: Bed) -> Decimal:
    room_type = bed.room.ward.room_type.name
    return as_money(DEFAULT_BED_RATES.get(room_type, Decimal("1500.00")))


def _bed_label(bed: Bed) -> str:
    return f"{bed.room.ward.name} / {bed.room.name} / {bed.code}"


def admission_payload(row: IpAdmission, *, detail: bool = False) -> dict:
    data = {
        "id": str(row.id),
        "ip_no": row.ip_no,
        "patient_id": str(row.patient_id),
        "patient_name": row.patient.full_name,
        "uhid": row.patient.uhid,
        "gender": row.patient.gender,
        "doctor_id": str(row.doctor_id),
        "doctor_name": row.doctor.name,
        "secondary_doctor_id": str(row.secondary_doctor_id) if row.secondary_doctor_id else "",
        "bed_id": str(row.bed_id),
        "bed_label": _bed_label(row.bed),
        "ward": row.bed.room.ward.name,
        "room": row.bed.room.name,
        "room_type": row.bed.room.ward.room_type.name,
        "admitted_at": row.admitted_at.isoformat(),
        "discharged_at": row.discharged_at.isoformat() if row.discharged_at else None,
        "status": row.status,
        "days": _stay_days(row),
        "bed_charge_per_day": str(row.bed_charge_per_day),
        "food_preference": row.food_preference,
        "diet": row.diet,
        "is_mlc": row.is_mlc,
        "is_vip": row.is_vip,
        "is_quarantine": row.is_quarantine,
        "insurance_covered": row.insurance_covered,
        "icd_code": row.icd_code,
        "attendant_name": row.attendant_name,
        "attendant_relation": row.attendant_relation,
        "attendant_mobile": row.attendant_mobile,
        "settlement_bill": bill_payload(row.settlement_bill) if row.settlement_bill_id else None,
        "remarks": row.remarks,
    }
    if detail:
        data["transfers"] = [
            {
                "id": str(t.id),
                "kind": t.kind,
                "from_doctor": t.from_doctor.name if t.from_doctor_id else "",
                "to_doctor": t.to_doctor.name if t.to_doctor_id else "",
                "from_bed": _bed_label(t.from_bed) if t.from_bed_id else "",
                "to_bed": _bed_label(t.to_bed) if t.to_bed_id else "",
                "reason": t.reason,
                "at": t.transferred_at.isoformat(),
            }
            for t in row.transfers.select_related(
                "from_doctor", "to_doctor", "from_bed__room__ward", "to_bed__room__ward"
            )
        ]
        data["daily_charges"] = [
            {
                "id": str(c.id),
                "charge_date": c.charge_date.isoformat(),
                "kind": c.kind,
                "description": c.description,
                "amount": str(c.amount),
                "bill_id": str(c.bill_id) if c.bill_id else "",
            }
            for c in row.daily_charges.all()
        ]
        data["nursing_notes"] = [
            {
                "id": str(n.id),
                "note": n.note,
                "temperature_c": str(n.temperature_c) if n.temperature_c is not None else None,
                "pulse": n.pulse,
                "bp_systolic": n.bp_systolic,
                "bp_diastolic": n.bp_diastolic,
                "spo2": n.spo2,
                "recorded_at": n.recorded_at.isoformat(),
                "recorded_by": n.recorded_by.get_username(),
            }
            for n in row.nursing_notes.select_related("recorded_by")[:50]
        ]
        data["doctor_orders"] = [
            {
                "id": str(o.id),
                "order_text": o.order_text,
                "status": o.status,
                "ordered_at": o.ordered_at.isoformat(),
                "ordered_by": o.ordered_by.get_username(),
            }
            for o in row.doctor_orders.select_related("ordered_by")[:50]
        ]
        data["mar"] = [
            {
                "id": str(m.id),
                "drug_name": m.drug_name,
                "dose": m.dose,
                "route": m.route,
                "given_at": m.given_at.isoformat(),
                "given_by": m.given_by.get_username(),
                "notes": m.notes,
            }
            for m in row.mar_entries.select_related("given_by")[:100]
        ]
        summary = getattr(row, "discharge_summary", None)
        data["discharge_summary"] = (
            {
                "condition_on_admission": summary.condition_on_admission,
                "condition_on_discharge": summary.condition_on_discharge,
                "chief_complaints": summary.chief_complaints,
                "diagnosis": summary.diagnosis,
                "surgery": summary.surgery,
                "treatment_given": summary.treatment_given,
                "treatment_advised": summary.treatment_advised,
                "investigations": summary.investigations,
                "icd_code": summary.icd_code,
                "next_visit_on": summary.next_visit_on.isoformat() if summary.next_visit_on else None,
            }
            if summary
            else None
        )
    return data


def _stay_days(row: IpAdmission) -> int:
    start = timezone.localdate(row.admitted_at)
    end = timezone.localdate(row.discharged_at) if row.discharged_at else facility_today(row.facility)
    return max(1, (end - start).days + 1)


@transaction.atomic
def admit(*, actor, facility, data, request=None) -> dict:
    require_permission(actor, facility, "ipd.admit")
    patient = _patient(facility, data.get("patient_id"))
    if IpAdmission.objects.filter(
        facility=facility, patient=patient, status=AdmissionStatus.ADMITTED
    ).exists():
        raise AppError("Patient already has an active admission.", code="conflict")
    doctor = _doctor(facility, data.get("doctor_id"))
    bed = _bed(facility, data.get("bed_id"))
    if bed.status != Bed.Status.VACANT:
        raise AppError("Bed is not vacant.", code="bed_unavailable")
    secondary = None
    if data.get("secondary_doctor_id"):
        secondary = _doctor(facility, data["secondary_doctor_id"])
    food = data.get("food_preference") or FoodPreference.VEG
    if food not in FoodPreference.values:
        raise AppError("Unknown food preference.", code="invalid")

    idempotency_key = (data.get("idempotency_key") or "").strip()
    if idempotency_key:
        existing = IpAdmission.objects.filter(facility=facility, idempotency_key=idempotency_key).first()
        if existing:
            return admission_payload(existing, detail=True)

    admitted_at = _parse_dt(data.get("admitted_at"), required=False) or timezone.now()
    rate = as_money(data.get("bed_charge_per_day") or _default_bed_rate(bed))
    ip_no = allocate(document_type=DocumentType.IP, facility=facility, on_date=facility_today(facility))
    visit = None
    if data.get("visit_id"):
        from apps.opd.models import Visit

        try:
            visit = Visit.objects.get(id=data["visit_id"], facility=facility, patient=patient)
        except Visit.DoesNotExist as exc:
            raise AppError("Visit not found.", code="not_found") from exc

    row = IpAdmission.objects.create(
        facility=facility,
        ip_no=ip_no,
        patient=patient,
        visit=visit,
        doctor=doctor,
        secondary_doctor=secondary,
        department=doctor.department,
        bed=bed,
        admitted_at=admitted_at,
        bed_charge_per_day=rate,
        food_preference=food,
        diet=(data.get("diet") or "").strip(),
        is_mlc=bool(data.get("is_mlc")),
        is_vip=bool(data.get("is_vip")),
        is_quarantine=bool(data.get("is_quarantine")),
        insurance_covered=bool(data.get("insurance_covered")),
        icd_code=(data.get("icd_code") or "").strip().upper(),
        attendant_name=(data.get("attendant_name") or "").strip(),
        attendant_relation=(data.get("attendant_relation") or "").strip(),
        attendant_mobile=(data.get("attendant_mobile") or "").strip(),
        admitted_by=actor,
        remarks=(data.get("remarks") or "").strip(),
        idempotency_key=idempotency_key,
    )
    bed.status = Bed.Status.OCCUPIED
    bed.save(update_fields=["status", "updated_at"])

    # Post first-day bed charge immediately.
    _post_day_charge(admission=row, actor=actor, on_date=timezone.localdate(admitted_at), request=request)

    advance_amount = as_money(data.get("advance_amount") or 0)
    if advance_amount > 0:
        take_advance(
            facility=facility,
            patient=patient,
            actor=actor,
            amount=advance_amount,
            mode=data.get("payment_mode") or PaymentMode.CASH,
            idempotency_key=f"ip-adv:{ip_no}",
        )

    record_audit(
        action="ipd.admit",
        actor=actor,
        facility=facility,
        entity_type="IpAdmission",
        entity_id=str(row.id),
        after={"ip_no": ip_no, "bed": _bed_label(bed)},
        request=request,
    )
    return admission_payload(row, detail=True)


def list_admissions(facility, *, status: str = "", q: str = "") -> list[dict]:
    qs = IpAdmission.objects.filter(facility=facility).select_related(
        "patient", "doctor", "bed__room__ward__room_type"
    )
    if status:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(
            Q(ip_no__icontains=q)
            | Q(patient__uhid__icontains=q)
            | Q(patient__full_name__icontains=q)
            | Q(patient__mobile__icontains=q)
        )
    return [admission_payload(r) for r in qs[:100]]


def get_admission(facility, admission_id) -> dict:
    return admission_payload(_admission(facility, admission_id), detail=True)


def bed_board(facility) -> dict:
    beds = Bed.objects.filter(room__ward__facility=facility, is_active=True).select_related(
        "room__ward__room_type"
    )
    active = {
        str(a.bed_id): a
        for a in IpAdmission.objects.filter(
            facility=facility, status=AdmissionStatus.ADMITTED
        ).select_related("patient", "doctor")
    }
    rows = []
    counts = {"VACANT": 0, "OCCUPIED": 0, "BLOCKED": 0, "total": 0}
    for bed in beds:
        counts["total"] += 1
        counts[bed.status] = counts.get(bed.status, 0) + 1
        adm = active.get(str(bed.id))
        rows.append(
            {
                "bed_id": str(bed.id),
                "code": bed.code,
                "status": bed.status,
                "ward": bed.room.ward.name,
                "room": bed.room.name,
                "room_type": bed.room.ward.room_type.name,
                "admission_id": str(adm.id) if adm else "",
                "ip_no": adm.ip_no if adm else "",
                "patient_name": adm.patient.full_name if adm else "",
                "doctor_name": adm.doctor.name if adm else "",
                "flags": {
                    "mlc": bool(adm and adm.is_mlc),
                    "vip": bool(adm and adm.is_vip),
                    "quarantine": bool(adm and adm.is_quarantine),
                }
                if adm
                else None,
            }
        )
    return {"counts": counts, "beds": rows}


@transaction.atomic
def transfer_doctor(*, actor, facility, admission_id, data, request=None) -> dict:
    require_permission(actor, facility, "ipd.transfer")
    row = _admission(facility, admission_id)
    if row.status != AdmissionStatus.ADMITTED:
        raise AppError("Only active admissions can be transferred.", code="invalid_status")
    to_doctor = _doctor(facility, data.get("doctor_id"))
    if to_doctor.id == row.doctor_id:
        raise AppError("Doctor is already assigned.", code="invalid")
    IpTransfer.objects.create(
        admission=row,
        kind=IpTransfer.Kind.DOCTOR,
        from_doctor=row.doctor,
        to_doctor=to_doctor,
        reason=(data.get("reason") or "").strip(),
        transferred_by=actor,
        transferred_at=timezone.now(),
    )
    row.doctor = to_doctor
    row.department = to_doctor.department
    row.save(update_fields=["doctor", "department", "updated_at"])
    record_audit(
        action="ipd.transfer.doctor",
        actor=actor,
        facility=facility,
        entity_type="IpAdmission",
        entity_id=str(row.id),
        after={"doctor": to_doctor.name},
        request=request,
    )
    return admission_payload(row, detail=True)


@transaction.atomic
def transfer_bed(*, actor, facility, admission_id, data, request=None) -> dict:
    require_permission(actor, facility, "ipd.transfer")
    row = _admission(facility, admission_id)
    if row.status != AdmissionStatus.ADMITTED:
        raise AppError("Only active admissions can be transferred.", code="invalid_status")
    new_bed = _bed(facility, data.get("bed_id"))
    if new_bed.id == row.bed_id:
        raise AppError("Patient is already on this bed.", code="invalid")
    if new_bed.status != Bed.Status.VACANT:
        raise AppError("Target bed is not vacant.", code="bed_unavailable")
    old_bed = row.bed
    IpTransfer.objects.create(
        admission=row,
        kind=IpTransfer.Kind.BED,
        from_bed=old_bed,
        to_bed=new_bed,
        reason=(data.get("reason") or "").strip(),
        transferred_by=actor,
        transferred_at=timezone.now(),
    )
    old_bed.status = Bed.Status.VACANT
    old_bed.save(update_fields=["status", "updated_at"])
    new_bed.status = Bed.Status.OCCUPIED
    new_bed.save(update_fields=["status", "updated_at"])
    row.bed = new_bed
    if data.get("bed_charge_per_day") is not None:
        row.bed_charge_per_day = as_money(data["bed_charge_per_day"])
    else:
        row.bed_charge_per_day = _default_bed_rate(new_bed)
    row.save(update_fields=["bed", "bed_charge_per_day", "updated_at"])
    record_audit(
        action="ipd.transfer.bed",
        actor=actor,
        facility=facility,
        entity_type="IpAdmission",
        entity_id=str(row.id),
        after={"bed": _bed_label(new_bed)},
        request=request,
    )
    return admission_payload(row, detail=True)


def _post_day_charge(*, admission: IpAdmission, actor, on_date: date, request=None) -> IpDailyCharge | None:
    if admission.status == AdmissionStatus.CANCELLED:
        return None
    existing = IpDailyCharge.objects.filter(
        admission=admission, charge_date=on_date, kind=IpDailyCharge.Kind.BED
    ).first()
    if existing:
        return existing
    amount = as_money(admission.bed_charge_per_day)
    nursing = Service.objects.filter(
        facility=admission.facility, code="NURSING", is_active=True, charge_unit="DAILY"
    ).first()
    lines = [
        ChargeLine(
            source_type="ipd",
            source_id=f"{admission.ip_no}:{on_date.isoformat()}:BED",
            description=f"IP bed charge {admission.ip_no} {on_date.isoformat()}",
            amount=amount,
            hospital_share=amount,
            doctor_share=zero(),
        )
    ]
    if nursing:
        n_amt = as_money(nursing.amount)
        lines.append(
            ChargeLine(
                source_type="ipd",
                source_id=f"{admission.ip_no}:{on_date.isoformat()}:NURSING",
                description=f"Nursing {admission.ip_no} {on_date.isoformat()}",
                amount=n_amt,
                hospital_share=as_money(nursing.hospital_share or n_amt),
                doctor_share=as_money(nursing.doctor_share or 0),
            )
        )
    bill = post_bill(
        facility=admission.facility,
        patient=admission.patient,
        actor=actor,
        lines=lines,
        paid=0,
        payment_mode=PaymentMode.CASH,
        idempotency_key=f"ip-day:{admission.ip_no}:{on_date.isoformat()}",
    )
    bed_charge = IpDailyCharge.objects.create(
        admission=admission,
        facility=admission.facility,
        charge_date=on_date,
        kind=IpDailyCharge.Kind.BED,
        description=f"Bed / room {on_date.isoformat()}",
        amount=amount,
        hospital_share=amount,
        doctor_share=zero(),
        bill=bill,
        posted_by=actor,
    )
    if nursing:
        IpDailyCharge.objects.get_or_create(
            admission=admission,
            charge_date=on_date,
            kind=IpDailyCharge.Kind.NURSING,
            defaults={
                "facility": admission.facility,
                "description": f"Nursing {on_date.isoformat()}",
                "amount": as_money(nursing.amount),
                "hospital_share": as_money(nursing.hospital_share or nursing.amount),
                "doctor_share": as_money(nursing.doctor_share or 0),
                "bill": bill,
                "posted_by": actor,
            },
        )
    record_audit(
        action="ipd.daily_charge",
        actor=actor,
        facility=admission.facility,
        entity_type="IpDailyCharge",
        entity_id=str(bed_charge.id),
        after={"date": on_date.isoformat(), "ip_no": admission.ip_no},
        request=request,
    )
    return bed_charge


@transaction.atomic
def post_daily_charges(*, actor, facility, data=None, request=None) -> dict:
    require_permission(actor, facility, "ipd.settle")
    data = data or {}
    on_date = parse_date(str(data.get("charge_date") or "")) or facility_today(facility)
    posted = []
    qs = IpAdmission.objects.filter(facility=facility, status=AdmissionStatus.ADMITTED)
    if data.get("admission_id"):
        qs = qs.filter(id=data["admission_id"])
    for admission in qs.select_related("patient", "bed__room__ward__room_type", "doctor"):
        if timezone.localdate(admission.admitted_at) > on_date:
            continue
        charge = _post_day_charge(admission=admission, actor=actor, on_date=on_date, request=request)
        if charge:
            posted.append({"admission_id": str(admission.id), "ip_no": admission.ip_no, "date": on_date.isoformat()})
    return {"posted": posted, "count": len(posted)}


@transaction.atomic
def add_nursing_note(*, actor, facility, admission_id, data, request=None) -> dict:
    require_permission(actor, facility, "ipd.nurse")
    row = _admission(facility, admission_id)
    if row.status != AdmissionStatus.ADMITTED:
        raise AppError("Admission is not active.", code="invalid_status")
    note = (data.get("note") or "").strip()
    if not note:
        raise AppError("Nursing note is required.", code="invalid")
    IpNursingNote.objects.create(
        admission=row,
        note=note,
        temperature_c=_dec(data.get("temperature_c")),
        pulse=int(data["pulse"]) if data.get("pulse") not in (None, "") else None,
        bp_systolic=int(data["bp_systolic"]) if data.get("bp_systolic") not in (None, "") else None,
        bp_diastolic=int(data["bp_diastolic"]) if data.get("bp_diastolic") not in (None, "") else None,
        spo2=int(data["spo2"]) if data.get("spo2") not in (None, "") else None,
        recorded_by=actor,
        recorded_at=timezone.now(),
    )
    if data.get("diet") is not None:
        row.diet = str(data.get("diet") or "").strip()
        row.save(update_fields=["diet", "updated_at"])
    record_audit(
        action="ipd.nursing_note",
        actor=actor,
        facility=facility,
        entity_type="IpAdmission",
        entity_id=str(row.id),
        request=request,
    )
    return admission_payload(row, detail=True)


@transaction.atomic
def add_doctor_order(*, actor, facility, admission_id, data, request=None) -> dict:
    require_permission(actor, facility, "ipd.order")
    row = _admission(facility, admission_id)
    if row.status != AdmissionStatus.ADMITTED:
        raise AppError("Admission is not active.", code="invalid_status")
    text = (data.get("order_text") or "").strip()
    if not text:
        raise AppError("Order text is required.", code="invalid")
    IpDoctorOrder.objects.create(
        admission=row,
        order_text=text,
        ordered_by=actor,
        ordered_at=timezone.now(),
    )
    record_audit(
        action="ipd.doctor_order",
        actor=actor,
        facility=facility,
        entity_type="IpAdmission",
        entity_id=str(row.id),
        request=request,
    )
    return admission_payload(row, detail=True)


@transaction.atomic
def add_mar(*, actor, facility, admission_id, data, request=None) -> dict:
    require_permission(actor, facility, "ipd.nurse")
    row = _admission(facility, admission_id)
    if row.status != AdmissionStatus.ADMITTED:
        raise AppError("Admission is not active.", code="invalid_status")
    drug = (data.get("drug_name") or "").strip()
    if not drug:
        raise AppError("Drug name is required.", code="invalid")
    IpMedicationAdmin.objects.create(
        admission=row,
        drug_name=drug,
        dose=(data.get("dose") or "").strip(),
        route=(data.get("route") or "").strip(),
        given_at=_parse_dt(data.get("given_at"), required=False) or timezone.now(),
        given_by=actor,
        notes=(data.get("notes") or "").strip(),
    )
    return admission_payload(row, detail=True)


@transaction.atomic
def save_discharge_summary(*, actor, facility, admission_id, data, request=None) -> dict:
    require_permission(actor, facility, "ipd.discharge")
    row = _admission(facility, admission_id)
    template = None
    if data.get("template_id"):
        try:
            template = DocumentTemplate.objects.get(
                id=data["template_id"], facility=facility, kind=DocumentTemplate.Kind.DISCHARGE
            )
        except DocumentTemplate.DoesNotExist as exc:
            raise AppError("Discharge template not found.", code="not_found") from exc
    defaults = {
        "template": template,
        "condition_on_admission": (data.get("condition_on_admission") or "").strip(),
        "condition_on_discharge": (data.get("condition_on_discharge") or "").strip(),
        "chief_complaints": (data.get("chief_complaints") or "").strip(),
        "diagnosis": (data.get("diagnosis") or "").strip(),
        "surgery": (data.get("surgery") or "").strip(),
        "treatment_given": (data.get("treatment_given") or "").strip(),
        "treatment_advised": (data.get("treatment_advised") or "").strip(),
        "investigations": (data.get("investigations") or "").strip(),
        "icd_code": (data.get("icd_code") or row.icd_code or "").strip().upper(),
        "discharged_by": actor,
    }
    next_visit = data.get("next_visit_on")
    if next_visit:
        defaults["next_visit_on"] = parse_date(str(next_visit))
    IpDischargeSummary.objects.update_or_create(admission=row, defaults=defaults)
    record_audit(
        action="ipd.discharge_summary",
        actor=actor,
        facility=facility,
        entity_type="IpAdmission",
        entity_id=str(row.id),
        request=request,
    )
    return admission_payload(row, detail=True)


def settlement_preview(facility, admission_id) -> dict:
    row = _admission(facility, admission_id)
    room_total = (
        row.daily_charges.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    )
    # Open patient bills during admission window (pharmacy/lab/radiology/ipd dues).
    start = row.admitted_at
    end = row.discharged_at or timezone.now()
    open_bills = list(
        Bill.objects.filter(
            facility=facility,
            patient=row.patient,
            created_at__gte=start - timedelta(minutes=1),
            created_at__lte=end + timedelta(days=1),
        ).prefetch_related("lines")
    )
    due_total = zero()
    breakdown = []
    for bill in open_bills:
        if bill.status == "CANCELLED":
            continue
        due = as_money(bill.due_amount)
        sources = {}
        for line in bill.lines.all():
            sources[line.source_type] = as_money(sources.get(line.source_type, 0) + line.amount)
        breakdown.append(
            {
                "bill_id": str(bill.id),
                "bill_no": bill.bill_no,
                "status": bill.status,
                "net_amount": str(bill.net_amount),
                "paid_amount": str(as_money(bill.paid_amount)),
                "due": str(max(due, zero())),
                "sources": {k: str(v) for k, v in sources.items()},
            }
        )
        due_total = as_money(due_total + max(due, zero()))
    advances = [
        a
        for a in Advance.objects.filter(facility=facility, patient=row.patient).order_by("created_at")
        if a.balance > 0
    ]
    advance_balance = as_money(sum((a.balance for a in advances), Decimal("0")))
    return {
        "admission_id": str(row.id),
        "ip_no": row.ip_no,
        "days": _stay_days(row),
        "room_charges_posted": str(as_money(room_total)),
        "open_due_total": str(due_total),
        "advance_balance": str(advance_balance),
        "estimated_payable": str(as_money(max(due_total - advance_balance, zero()))),
        "bills": breakdown,
        "advances": [
            {"id": str(a.id), "advance_no": a.advance_no, "balance": str(a.balance)} for a in advances
        ],
    }


@transaction.atomic
def settle_and_discharge(*, actor, facility, admission_id, data=None, request=None) -> dict:
    require_permission(actor, facility, "ipd.settle")
    data = data or {}
    row = _admission(facility, admission_id)
    if row.status != AdmissionStatus.ADMITTED:
        raise AppError("Admission is not active.", code="invalid_status")
    try:
        _ = row.discharge_summary
        has_summary = True
    except IpDischargeSummary.DoesNotExist:
        has_summary = False
    if not has_summary:
        if not (data.get("diagnosis") or data.get("condition_on_discharge")):
            raise AppError(
                "Save a discharge summary (or provide diagnosis) before settlement.",
                code="invalid",
            )
        save_discharge_summary(
            actor=actor, facility=facility, admission_id=admission_id, data=data, request=request
        )
        row = _admission(facility, admission_id)

    # Ensure charges through discharge date.
    discharge_at = _parse_dt(data.get("discharged_at"), required=False) or timezone.now()
    day = timezone.localdate(row.admitted_at)
    last = timezone.localdate(discharge_at)
    while day <= last:
        _post_day_charge(admission=row, actor=actor, on_date=day, request=request)
        day += timedelta(days=1)

    preview = settlement_preview(facility, admission_id)
    # Apply advances to open dues (oldest first).
    for bill_row in Bill.objects.filter(
        facility=facility,
        patient=row.patient,
        created_at__gte=row.admitted_at - timedelta(minutes=1),
    ).order_by("created_at"):
        if bill_row.status == "CANCELLED":
            continue
        due = as_money(bill_row.due_amount)
        if due <= 0:
            continue
        for advance in Advance.objects.filter(facility=facility, patient=row.patient).order_by(
            "created_at"
        ):
            if advance.balance <= 0:
                continue
            bill_row.refresh_from_db()
            due = as_money(bill_row.due_amount)
            if due <= 0:
                break
            apply_amt = min(as_money(advance.balance), due)
            if apply_amt <= 0:
                continue
            apply_advance(
                advance=advance,
                bill=bill_row,
                actor=actor,
                amount=apply_amt,
                idempotency_key=f"ip-settle:{row.ip_no}:{bill_row.bill_no}:{advance.advance_no}",
            )

    row.status = AdmissionStatus.DISCHARGED
    row.discharged_at = discharge_at
    # Keep last IP daily bill as settlement pointer if present.
    last_charge = row.daily_charges.order_by("-charge_date").first()
    if last_charge and last_charge.bill_id:
        row.settlement_bill = last_charge.bill
    row.save(update_fields=["status", "discharged_at", "settlement_bill", "updated_at"])
    row.bed.status = Bed.Status.VACANT
    row.bed.save(update_fields=["status", "updated_at"])
    record_audit(
        action="ipd.discharge",
        actor=actor,
        facility=facility,
        entity_type="IpAdmission",
        entity_id=str(row.id),
        after={"ip_no": row.ip_no, "preview": preview},
        request=request,
    )
    payload = admission_payload(row, detail=True)
    payload["settlement"] = settlement_preview(facility, admission_id)
    return payload


@transaction.atomic
def cancel_discharge(*, actor, facility, admission_id, data, request=None) -> dict:
    require_permission(actor, facility, "ipd.discharge")
    row = _admission(facility, admission_id)
    if row.status != AdmissionStatus.DISCHARGED:
        raise AppError("Only discharged admissions can be reopened.", code="invalid_status")
    reason = (data.get("reason") or "").strip()
    if not reason:
        raise AppError("Cancel reason is required.", code="invalid")
    if row.bed.status != Bed.Status.VACANT:
        raise AppError("Original bed is no longer vacant; transfer after reopen.", code="bed_unavailable")
    if IpAdmission.objects.filter(
        facility=facility, patient=row.patient, status=AdmissionStatus.ADMITTED
    ).exists():
        raise AppError("Patient already has another active admission.", code="conflict")
    row.status = AdmissionStatus.ADMITTED
    row.discharged_at = None
    row.cancel_reason = reason
    row.save(update_fields=["status", "discharged_at", "cancel_reason", "updated_at"])
    row.bed.status = Bed.Status.OCCUPIED
    row.bed.save(update_fields=["status", "updated_at"])
    record_audit(
        action="ipd.discharge.cancel",
        actor=actor,
        facility=facility,
        entity_type="IpAdmission",
        entity_id=str(row.id),
        after={"reason": reason},
        request=request,
    )
    return admission_payload(row, detail=True)


@transaction.atomic
def cancel_admission(*, actor, facility, admission_id, data, request=None) -> dict:
    require_permission(actor, facility, "ipd.admit")
    row = _admission(facility, admission_id)
    if row.status != AdmissionStatus.ADMITTED:
        raise AppError("Only active admissions can be cancelled.", code="invalid_status")
    reason = (data.get("reason") or "").strip()
    if not reason:
        raise AppError("Cancel reason is required.", code="invalid")
    row.status = AdmissionStatus.CANCELLED
    row.cancel_reason = reason
    row.discharged_at = timezone.now()
    row.save(update_fields=["status", "cancel_reason", "discharged_at", "updated_at"])
    row.bed.status = Bed.Status.VACANT
    row.bed.save(update_fields=["status", "updated_at"])
    record_audit(
        action="ipd.admit.cancel",
        actor=actor,
        facility=facility,
        entity_type="IpAdmission",
        entity_id=str(row.id),
        after={"reason": reason},
        request=request,
    )
    return admission_payload(row, detail=True)


@transaction.atomic
def issue_certificate(*, actor, facility, data, request=None) -> dict:
    require_permission(actor, facility, "ipd.certificate")
    kind = data.get("kind")
    if kind not in CertificateKind.values:
        raise AppError("Unknown certificate type.", code="invalid")
    admission = None
    if data.get("admission_id"):
        admission = _admission(facility, data["admission_id"])
        patient = admission.patient
    else:
        patient = _patient(facility, data.get("patient_id"))
    seq = MedicalCertificate.objects.filter(facility=facility).count() + 1
    prefix = admission.ip_no if admission else patient.uhid
    cert_no = f"MC-{prefix}-{seq:04d}"
    row = MedicalCertificate.objects.create(
        facility=facility,
        admission=admission,
        patient=patient,
        cert_no=cert_no,
        kind=kind,
        disease_name=(data.get("disease_name") or "").strip(),
        occupation=(data.get("occupation") or "").strip(),
        body=(data.get("body") or "").strip(),
        fit_on=parse_date(str(data["fit_on"])) if data.get("fit_on") else None,
        rest_from=parse_date(str(data["rest_from"])) if data.get("rest_from") else None,
        rest_to=parse_date(str(data["rest_to"])) if data.get("rest_to") else None,
        birth_details=(data.get("birth_details") or "").strip(),
        birth_on=parse_date(str(data["birth_on"])) if data.get("birth_on") else None,
        death_on=parse_date(str(data["death_on"])) if data.get("death_on") else None,
        death_time=(data.get("death_time") or "").strip(),
        issued_by=actor,
        issued_at=timezone.now(),
    )
    record_audit(
        action="ipd.certificate.issue",
        actor=actor,
        facility=facility,
        entity_type="MedicalCertificate",
        entity_id=str(row.id),
        after={"cert_no": cert_no, "kind": kind},
        request=request,
    )
    return certificate_payload(row)


def certificate_payload(row: MedicalCertificate) -> dict:
    return {
        "id": str(row.id),
        "cert_no": row.cert_no,
        "kind": row.kind,
        "patient_id": str(row.patient_id),
        "patient_name": row.patient.full_name,
        "uhid": row.patient.uhid,
        "admission_id": str(row.admission_id) if row.admission_id else "",
        "ip_no": row.admission.ip_no if row.admission_id else "",
        "disease_name": row.disease_name,
        "occupation": row.occupation,
        "body": row.body,
        "fit_on": row.fit_on.isoformat() if row.fit_on else None,
        "rest_from": row.rest_from.isoformat() if row.rest_from else None,
        "rest_to": row.rest_to.isoformat() if row.rest_to else None,
        "birth_details": row.birth_details,
        "birth_on": row.birth_on.isoformat() if row.birth_on else None,
        "death_on": row.death_on.isoformat() if row.death_on else None,
        "death_time": row.death_time,
        "issued_at": row.issued_at.isoformat(),
    }


def list_certificates(facility, *, admission_id: str = "") -> list[dict]:
    qs = MedicalCertificate.objects.filter(facility=facility).select_related("patient", "admission")
    if admission_id:
        qs = qs.filter(admission_id=admission_id)
    return [certificate_payload(r) for r in qs[:50]]
