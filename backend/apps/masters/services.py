"""Master data rules. Views validate shape; this module checks facility scope and money."""

from __future__ import annotations

from decimal import Decimal

from django.db import IntegrityError, transaction

from apps.audit.services import record_audit
from apps.billing.models import PaymentMode, TaxCategory
from apps.common.exceptions import AppError, ConflictError
from apps.common.money import money
from apps.masters.models import (
    PRO,
    Area,
    Bed,
    City,
    Country,
    Department,
    DiscountRule,
    Doctor,
    DoctorSchedule,
    DocumentTemplate,
    OrganizationParty,
    PaymentModeConfig,
    Procedure,
    ReferralDoctor,
    Room,
    RoomType,
    Service,
    Specialization,
    State,
    Tariff,
    Ward,
)


def _owned(model, facility, row_id):
    try:
        return model.objects.get(id=row_id, facility=facility)
    except model.DoesNotExist as exc:
        raise AppError("Record not found in this facility.", code="not_found") from exc


def _shares(amount, hospital, doctor):
    amount, hospital, doctor = money(amount), money(hospital), money(doctor)
    if amount < 0 or hospital < 0 or doctor < 0:
        raise AppError("Amounts cannot be negative.", code="bad_shares")
    if hospital + doctor != amount:
        raise AppError(
            "Hospital share and doctor share must add up to the amount.",
            code="bad_shares",
        )
    return amount, hospital, doctor


def _flag(data, key, default=True):
    if key not in data:
        return default
    return bool(data[key])


def _audit(actor, facility, action, row, request):
    record_audit(
        action=action,
        actor=actor,
        facility=facility,
        entity_type=row.__class__.__name__,
        entity_id=str(row.id),
        after={"name": getattr(row, "name", None) or getattr(row, "code", "")},
        request=request,
    )


def _save(row):
    try:
        with transaction.atomic():
            row.save()
    except IntegrityError as exc:
        raise ConflictError("A record with that name or code already exists.", code="duplicate") from exc
    return row


def list_departments(facility):
    return [
        {"id": str(r.id), "name": r.name, "is_active": r.is_active}
        for r in Department.objects.filter(facility=facility)
    ]


def create_department(facility, actor, data, request=None):
    row = Department(facility=facility, name=(data.get("name") or "").strip(), is_active=_flag(data, "is_active"))
    if not row.name:
        raise AppError("Name is required.", code="invalid")
    _save(row)
    _audit(actor, facility, "masters.department.create", row, request)
    return {"id": str(row.id), "name": row.name, "is_active": row.is_active}


def update_department(facility, actor, row_id, data, request=None):
    row = _owned(Department, facility, row_id)
    if "name" in data:
        row.name = (data.get("name") or "").strip()
    if "is_active" in data:
        row.is_active = bool(data["is_active"])
    _save(row)
    _audit(actor, facility, "masters.department.update", row, request)
    return {"id": str(row.id), "name": row.name, "is_active": row.is_active}


def list_specializations(facility):
    rows = Specialization.objects.filter(facility=facility).select_related("department")
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "department_id": str(r.department_id),
            "department": r.department.name,
            "is_active": r.is_active,
        }
        for r in rows
    ]


def create_specialization(facility, actor, data, request=None):
    department = _owned(Department, facility, data.get("department_id"))
    row = Specialization(
        facility=facility,
        department=department,
        name=(data.get("name") or "").strip(),
        is_active=_flag(data, "is_active"),
    )
    if not row.name:
        raise AppError("Name is required.", code="invalid")
    _save(row)
    _audit(actor, facility, "masters.specialization.create", row, request)
    return {"id": str(row.id), "name": row.name, "department_id": str(department.id), "is_active": row.is_active}


def list_doctors(facility):
    rows = Doctor.objects.filter(facility=facility).select_related("department", "specialization")
    return [
        {
            "id": str(r.id),
            "code": r.code,
            "name": r.name,
            "department_id": str(r.department_id),
            "department": r.department.name,
            "specialization_id": str(r.specialization_id),
            "specialization": r.specialization.name,
            "consultation_fee": str(r.consultation_fee),
            "hospital_share": str(r.hospital_share),
            "doctor_share": str(r.doctor_share),
            "review_days": r.review_days,
            "is_active": r.is_active,
            "schedules": [
                {
                    "id": str(s.id),
                    "weekday": s.weekday,
                    "start_time": s.start_time.strftime("%H:%M"),
                    "end_time": s.end_time.strftime("%H:%M"),
                    "slot_minutes": s.slot_minutes,
                }
                for s in r.schedules.all()
            ],
        }
        for r in rows
    ]


def create_doctor(facility, actor, data, request=None):
    department = _owned(Department, facility, data.get("department_id"))
    spec = _owned(Specialization, facility, data.get("specialization_id"))
    if spec.department_id != department.id:
        raise AppError("Specialization does not belong to that department.", code="invalid")
    fee, hospital, doctor_share = _shares(
        data.get("consultation_fee") or 0,
        data.get("hospital_share") or 0,
        data.get("doctor_share") or 0,
    )
    row = Doctor(
        facility=facility,
        code=(data.get("code") or "").strip().upper(),
        name=(data.get("name") or "").strip(),
        department=department,
        specialization=spec,
        consultation_fee=fee,
        hospital_share=hospital,
        doctor_share=doctor_share,
        review_days=int(data.get("review_days") or 7),
        is_active=_flag(data, "is_active"),
    )
    if not row.code or not row.name:
        raise AppError("Code and name are required.", code="invalid")
    _save(row)
    _audit(actor, facility, "masters.doctor.create", row, request)
    return {"id": str(row.id), "code": row.code, "name": row.name}


def update_doctor(facility, actor, row_id, data, request=None):
    row = _owned(Doctor, facility, row_id)
    if "name" in data:
        row.name = (data.get("name") or "").strip()
    if "is_active" in data:
        row.is_active = bool(data["is_active"])
    if "review_days" in data:
        row.review_days = int(data["review_days"])
    if any(k in data for k in ("consultation_fee", "hospital_share", "doctor_share")):
        fee, hospital, doctor_share = _shares(
            data.get("consultation_fee", row.consultation_fee),
            data.get("hospital_share", row.hospital_share),
            data.get("doctor_share", row.doctor_share),
        )
        row.consultation_fee, row.hospital_share, row.doctor_share = fee, hospital, doctor_share
    _save(row)
    _audit(actor, facility, "masters.doctor.update", row, request)
    return {"id": str(row.id), "code": row.code, "name": row.name}


def set_schedule(facility, actor, data, request=None):
    doctor = _owned(Doctor, facility, data.get("doctor_id"))
    weekday = int(data.get("weekday"))
    if weekday < 0 or weekday > 6:
        raise AppError("Weekday must be 0 (Monday) through 6 (Sunday).", code="invalid")
    start = data.get("start_time")
    end = data.get("end_time")
    if not start or not end or start >= end:
        raise AppError("End time must be after start time.", code="invalid")
    row, _created = DoctorSchedule.objects.update_or_create(
        doctor=doctor,
        weekday=weekday,
        defaults={
            "start_time": start,
            "end_time": end,
            "slot_minutes": int(data.get("slot_minutes") or 15),
        },
    )
    _audit(actor, facility, "masters.schedule.update", doctor, request)
    return {"id": str(row.id), "doctor_id": str(doctor.id), "weekday": weekday}


def list_referrals(facility):
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "hospital": r.hospital,
            "mobile": r.mobile,
            "address": r.address,
            "email": r.email,
            "commission_percent": str(r.commission_percent),
            "is_active": r.is_active,
        }
        for r in ReferralDoctor.objects.filter(facility=facility)
    ]


def create_referral(facility, actor, data, request=None):
    name = (data.get("name") or "").strip()
    if not name:
        raise AppError("Name is required.", code="invalid")
    row = ReferralDoctor(
        facility=facility,
        name=name,
        hospital=(data.get("hospital") or "").strip(),
        mobile=(data.get("mobile") or "").strip(),
        address=(data.get("address") or "").strip(),
        email=(data.get("email") or "").strip(),
        commission_percent=money(data.get("commission_percent") or 0),
        is_active=_flag(data, "is_active"),
    )
    _save(row)
    _audit(actor, facility, "masters.referral.create", row, request)
    return {"id": str(row.id), "name": row.name}


def list_pros(facility):
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "mobile": r.mobile,
            "commission_percent": str(r.commission_percent),
            "is_active": r.is_active,
        }
        for r in PRO.objects.filter(facility=facility)
    ]


def create_pro(facility, actor, data, request=None):
    name = (data.get("name") or "").strip()
    if not name:
        raise AppError("Name is required.", code="invalid")
    row = PRO(
        facility=facility,
        name=name,
        mobile=(data.get("mobile") or "").strip(),
        commission_percent=money(data.get("commission_percent") or 0),
        is_active=_flag(data, "is_active"),
    )
    _save(row)
    _audit(actor, facility, "masters.pro.create", row, request)
    return {"id": str(row.id), "name": row.name}


def list_parties(facility):
    return [
        {"id": str(r.id), "name": r.name, "kind": r.kind, "is_active": r.is_active}
        for r in OrganizationParty.objects.filter(facility=facility)
    ]


def create_party(facility, actor, data, request=None):
    name = (data.get("name") or "").strip()
    kind = data.get("kind")
    if kind not in OrganizationParty.Kind.values:
        raise AppError("Kind must be CORPORATE or TPA.", code="invalid")
    if not name:
        raise AppError("Name is required.", code="invalid")
    row = OrganizationParty(facility=facility, name=name, kind=kind, is_active=_flag(data, "is_active"))
    _save(row)
    _audit(actor, facility, "masters.party.create", row, request)
    return {"id": str(row.id), "name": row.name, "kind": row.kind}


def _charge_row(row):
    return {
        "id": str(row.id),
        "code": row.code,
        "name": row.name,
        "description": row.description,
        "amount": str(row.amount),
        "hospital_share": str(row.hospital_share),
        "doctor_share": str(row.doctor_share),
        "is_active": row.is_active,
    }


def list_procedures(facility):
    rows = []
    for row in Procedure.objects.filter(facility=facility):
        payload = _charge_row(row)
        payload["is_doctor_procedure"] = row.is_doctor_procedure
        rows.append(payload)
    return rows


def create_procedure(facility, actor, data, request=None):
    amount, hospital, doctor_share = _shares(
        data.get("amount") or 0, data.get("hospital_share") or 0, data.get("doctor_share") or 0
    )
    row = Procedure(
        facility=facility,
        code=(data.get("code") or "").strip().upper(),
        name=(data.get("name") or "").strip(),
        description=(data.get("description") or "").strip(),
        amount=amount,
        hospital_share=hospital,
        doctor_share=doctor_share,
        is_doctor_procedure=bool(data.get("is_doctor_procedure")),
        is_active=_flag(data, "is_active"),
    )
    if not row.code or not row.name:
        raise AppError("Code and name are required.", code="invalid")
    _save(row)
    _audit(actor, facility, "masters.procedure.create", row, request)
    return _charge_row(row)


def list_services(facility):
    rows = []
    for row in Service.objects.filter(facility=facility):
        payload = _charge_row(row)
        payload["service_type"] = row.service_type
        payload["charge_unit"] = row.charge_unit
        rows.append(payload)
    return rows


def create_service(facility, actor, data, request=None):
    if data.get("service_type") not in Service.ServiceType.values:
        raise AppError("Service type is required.", code="invalid")
    if data.get("charge_unit") not in Service.ChargeUnit.values:
        raise AppError("Charge unit is required.", code="invalid")
    amount, hospital, doctor_share = _shares(
        data.get("amount") or 0, data.get("hospital_share") or 0, data.get("doctor_share") or 0
    )
    row = Service(
        facility=facility,
        code=(data.get("code") or "").strip().upper(),
        name=(data.get("name") or "").strip(),
        description=(data.get("description") or "").strip(),
        service_type=data["service_type"],
        charge_unit=data["charge_unit"],
        amount=amount,
        hospital_share=hospital,
        doctor_share=doctor_share,
        is_active=_flag(data, "is_active"),
    )
    if not row.code or not row.name:
        raise AppError("Code and name are required.", code="invalid")
    _save(row)
    _audit(actor, facility, "masters.service.create", row, request)
    payload = _charge_row(row)
    payload["service_type"] = row.service_type
    payload["charge_unit"] = row.charge_unit
    return payload


def list_room_types(facility):
    return [
        {"id": str(r.id), "name": r.name, "is_active": r.is_active}
        for r in RoomType.objects.filter(facility=facility)
    ]


def create_room_type(facility, actor, data, request=None):
    name = (data.get("name") or "").strip()
    if not name:
        raise AppError("Name is required.", code="invalid")
    row = RoomType(facility=facility, name=name, is_active=_flag(data, "is_active"))
    _save(row)
    _audit(actor, facility, "masters.room_type.create", row, request)
    return {"id": str(row.id), "name": row.name}


def list_wards(facility):
    rows = Ward.objects.filter(facility=facility).select_related("room_type")
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "room_type_id": str(r.room_type_id),
            "room_type": r.room_type.name,
            "is_active": r.is_active,
            "rooms": [
                {
                    "id": str(room.id),
                    "name": room.name,
                    "beds": [
                        {"id": str(b.id), "code": b.code, "status": b.status, "is_active": b.is_active}
                        for b in room.beds.all()
                    ],
                }
                for room in r.rooms.all()
            ],
        }
        for r in rows
    ]


def create_ward(facility, actor, data, request=None):
    room_type = _owned(RoomType, facility, data.get("room_type_id"))
    name = (data.get("name") or "").strip()
    if not name:
        raise AppError("Name is required.", code="invalid")
    row = Ward(facility=facility, name=name, room_type=room_type, is_active=_flag(data, "is_active"))
    _save(row)
    _audit(actor, facility, "masters.ward.create", row, request)
    return {"id": str(row.id), "name": row.name, "room_type_id": str(room_type.id)}


def create_room(facility, actor, data, request=None):
    ward = _owned(Ward, facility, data.get("ward_id"))
    name = (data.get("name") or "").strip()
    if not name:
        raise AppError("Room name is required.", code="invalid")
    row = Room(ward=ward, name=name, is_active=_flag(data, "is_active"))
    _save(row)
    _audit(actor, facility, "masters.room.create", ward, request)
    return {"id": str(row.id), "name": row.name, "ward_id": str(ward.id)}


def create_bed(facility, actor, data, request=None):
    room = Room.objects.select_related("ward").filter(id=data.get("room_id"), ward__facility=facility).first()
    if not room:
        raise AppError("Room not found in this facility.", code="not_found")
    code = (data.get("code") or "").strip().upper()
    if not code:
        raise AppError("Bed code is required.", code="invalid")
    status = data.get("status") or Bed.Status.VACANT
    if status not in Bed.Status.values:
        raise AppError("Unknown bed status.", code="invalid")
    row = Bed(room=room, code=code, status=status, is_active=_flag(data, "is_active"))
    _save(row)
    _audit(actor, facility, "masters.bed.create", room.ward, request)
    return {"id": str(row.id), "code": row.code, "status": row.status, "room_id": str(room.id)}


def list_tariffs(facility):
    rows = Tariff.objects.filter(facility=facility).select_related("procedure", "service", "doctor", "party")
    return [
        {
            "id": str(r.id),
            "kind": r.kind,
            "procedure": r.procedure.name if r.procedure_id else "",
            "service": r.service.name if r.service_id else "",
            "doctor": r.doctor.name if r.doctor_id else "",
            "party": r.party.name if r.party_id else "Hospital cash",
            "hospital_share": str(r.hospital_share),
            "doctor_share": str(r.doctor_share),
            "amount": str(money(r.hospital_share) + money(r.doctor_share)),
            "is_active": r.is_active,
        }
        for r in rows
    ]


def _scale(row, multiplier: Decimal):
    hospital = money(row.hospital_share * multiplier)
    doctor_share = money(row.doctor_share * multiplier)
    if hasattr(row, "amount"):
        row.amount = money(hospital + doctor_share)
    if hasattr(row, "consultation_fee"):
        row.consultation_fee = money(hospital + doctor_share)
    row.hospital_share = hospital
    row.doctor_share = doctor_share
    row.save()


@transaction.atomic
def adjust_charges(facility, actor, data, request=None):
    percent = money(data.get("percent") or 0)
    direction = data.get("direction")
    kind = data.get("kind") or "ALL"
    if percent <= 0 or percent > 100:
        raise AppError("Percent must be greater than 0 and at most 100.", code="bad_adjustment")
    if direction not in ("UP", "DOWN"):
        raise AppError("Direction must be UP or DOWN.", code="bad_adjustment")
    if kind not in ("ALL", "PROCEDURE", "SERVICE", "DOCTOR"):
        raise AppError("Kind must be ALL, PROCEDURE, SERVICE, or DOCTOR.", code="bad_adjustment")
    multiplier = Decimal("1") + (percent / Decimal("100")) * (1 if direction == "UP" else -1)
    if multiplier <= 0:
        raise AppError("Adjustment would remove the charge.", code="bad_adjustment")
    count = 0
    if kind in ("ALL", "PROCEDURE"):
        for row in Procedure.objects.filter(facility=facility, is_active=True):
            _scale(row, multiplier)
            count += 1
    if kind in ("ALL", "SERVICE"):
        for row in Service.objects.filter(facility=facility, is_active=True):
            _scale(row, multiplier)
            count += 1
    if kind in ("ALL", "DOCTOR"):
        for row in Doctor.objects.filter(facility=facility, is_active=True):
            _scale(row, multiplier)
            count += 1
    for row in Tariff.objects.filter(facility=facility, is_active=True):
        if kind == "ALL" or row.kind == kind or (kind == "DOCTOR" and row.doctor_id):
            _scale(row, multiplier)
            count += 1
    record_audit(
        action="masters.tariff.adjust",
        actor=actor,
        facility=facility,
        entity_type="Tariff",
        after={"percent": str(percent), "direction": direction, "kind": kind, "rows": count},
        request=request,
    )
    return {"updated": count, "direction": direction, "percent": str(percent)}


@transaction.atomic
def copy_tariffs(facility, actor, data, request=None):
    party = _owned(OrganizationParty, facility, data.get("party_id"))
    copied = 0
    for proc in Procedure.objects.filter(facility=facility, is_active=True):
        Tariff.objects.update_or_create(
            facility=facility,
            kind=Tariff.Kind.PROCEDURE,
            procedure=proc,
            service=None,
            doctor=None,
            party=party,
            defaults={
                "hospital_share": proc.hospital_share,
                "doctor_share": proc.doctor_share,
                "is_active": True,
            },
        )
        copied += 1
    for service in Service.objects.filter(facility=facility, is_active=True):
        Tariff.objects.update_or_create(
            facility=facility,
            kind=Tariff.Kind.SERVICE,
            procedure=None,
            service=service,
            doctor=None,
            party=party,
            defaults={
                "hospital_share": service.hospital_share,
                "doctor_share": service.doctor_share,
                "is_active": True,
            },
        )
        copied += 1
    record_audit(
        action="masters.tariff.copy",
        actor=actor,
        facility=facility,
        entity_type="OrganizationParty",
        entity_id=str(party.id),
        after={"party": party.name, "rows": copied},
        request=request,
    )
    return {"copied": copied, "party": party.name}


def list_discount_rules(facility):
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "max_percent": str(r.max_percent),
            "max_flat": str(r.max_flat),
            "is_active": r.is_active,
        }
        for r in DiscountRule.objects.filter(facility=facility)
    ]


def create_discount_rule(facility, actor, data, request=None):
    name = (data.get("name") or "").strip()
    if not name:
        raise AppError("Name is required.", code="invalid")
    percent = money(data.get("max_percent") or 0)
    flat = money(data.get("max_flat") or 0)
    if percent < 0 or percent > 100 or flat < 0:
        raise AppError("Discount limits are out of range.", code="invalid")
    row = DiscountRule(
        facility=facility,
        name=name,
        max_percent=percent,
        max_flat=flat,
        is_active=_flag(data, "is_active"),
    )
    _save(row)
    _audit(actor, facility, "masters.discount_rule.create", row, request)
    return {"id": str(row.id), "name": row.name, "max_percent": str(row.max_percent), "max_flat": str(row.max_flat)}


def update_discount_rule(facility, actor, row_id, data, request=None):
    row = _owned(DiscountRule, facility, row_id)
    if "is_active" in data:
        row.is_active = bool(data["is_active"])
    if "max_percent" in data:
        row.max_percent = money(data["max_percent"])
    if "max_flat" in data:
        row.max_flat = money(data["max_flat"])
    _save(row)
    _audit(actor, facility, "masters.discount_rule.update", row, request)
    return {"id": str(row.id), "name": row.name, "is_active": row.is_active}


def list_payment_modes(facility):
    return [
        {"id": str(r.id), "code": r.code, "name": r.name, "is_active": r.is_active}
        for r in PaymentModeConfig.objects.filter(facility=facility)
    ]


def update_payment_mode(facility, actor, row_id, data, request=None):
    row = _owned(PaymentModeConfig, facility, row_id)
    if row.code == PaymentMode.ADVANCE:
        raise AppError("Advance adjustment is a system mode.", code="invalid")
    if "is_active" in data:
        row.is_active = bool(data["is_active"])
    if "name" in data and (data.get("name") or "").strip():
        row.name = data["name"].strip()
    _save(row)
    _audit(actor, facility, "masters.payment_mode.update", row, request)
    return {"id": str(row.id), "code": row.code, "name": row.name, "is_active": row.is_active}


def assert_payment_mode_active(facility, mode: str) -> None:
    config = PaymentModeConfig.objects.filter(facility=facility, code=mode).first()
    if config is not None and not config.is_active:
        raise AppError(f"{config.name} is not an active payment mode.", code="bad_payment")


def facility_discount_ceiling(facility):
    rules = list(DiscountRule.objects.filter(facility=facility, is_active=True))
    if not rules:
        return None
    return min(r.max_percent for r in rules), min(r.max_flat for r in rules)


def list_taxes(facility):
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "hsn_sac": r.hsn_sac,
            "rate_percent": str(r.rate_percent),
            "is_active": r.is_active,
        }
        for r in TaxCategory.objects.filter(facility=facility)
    ]


def create_tax(facility, actor, data, request=None):
    name = (data.get("name") or "").strip()
    if not name:
        raise AppError("Name is required.", code="invalid")
    rate = money(data.get("rate_percent") or 0)
    if rate < 0 or rate > 100:
        raise AppError("Tax rate must be between 0 and 100.", code="invalid")
    row = TaxCategory(
        facility=facility,
        name=name,
        hsn_sac=(data.get("hsn_sac") or "").strip(),
        rate_percent=rate,
        is_active=_flag(data, "is_active"),
    )
    _save(row)
    _audit(actor, facility, "masters.tax.create", row, request)
    return {"id": str(row.id), "name": row.name, "rate_percent": str(row.rate_percent)}


def list_templates(facility):
    return [
        {
            "id": str(r.id),
            "kind": r.kind,
            "certificate_type": r.certificate_type,
            "name": r.name,
            "body": r.body,
            "is_active": r.is_active,
        }
        for r in DocumentTemplate.objects.filter(facility=facility)
    ]


def create_template(facility, actor, data, request=None):
    kind = data.get("kind")
    if kind not in DocumentTemplate.Kind.values:
        raise AppError("Template kind is required.", code="invalid")
    certificate_type = data.get("certificate_type") or ""
    if certificate_type and certificate_type not in DocumentTemplate.CertificateType.values:
        raise AppError("Unknown certificate type.", code="invalid")
    name = (data.get("name") or "").strip()
    if not name:
        raise AppError("Name is required.", code="invalid")
    row = DocumentTemplate(
        facility=facility,
        kind=kind,
        certificate_type=certificate_type,
        name=name,
        body=data.get("body") or "",
        is_active=_flag(data, "is_active"),
    )
    _save(row)
    _audit(actor, facility, "masters.template.create", row, request)
    return {"id": str(row.id), "name": row.name, "kind": row.kind}


def list_countries():
    return [{"id": str(r.id), "name": r.name} for r in Country.objects.all()]


def create_country(actor, facility, data, request=None):
    name = (data.get("name") or "").strip()
    if not name:
        raise AppError("Name is required.", code="invalid")
    row = Country(name=name)
    _save(row)
    _audit(actor, facility, "masters.country.create", row, request)
    return {"id": str(row.id), "name": row.name}


def list_states():
    return [
        {"id": str(r.id), "name": r.name, "country_id": str(r.country_id), "country": r.country.name}
        for r in State.objects.select_related("country")
    ]


def create_state(actor, facility, data, request=None):
    try:
        country = Country.objects.get(id=data.get("country_id"))
    except Country.DoesNotExist as exc:
        raise AppError("Country not found.", code="not_found") from exc
    name = (data.get("name") or "").strip()
    if not name:
        raise AppError("Name is required.", code="invalid")
    row = State(country=country, name=name)
    _save(row)
    _audit(actor, facility, "masters.state.create", row, request)
    return {"id": str(row.id), "name": row.name}


def list_cities():
    rows = City.objects.select_related("state", "state__country")
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "state_id": str(r.state_id),
            "state": r.state.name,
            "country": r.state.country.name,
        }
        for r in rows
    ]


def create_city(actor, facility, data, request=None):
    try:
        state = State.objects.select_related("country").get(id=data.get("state_id"))
    except State.DoesNotExist as exc:
        raise AppError("State not found.", code="not_found") from exc
    name = (data.get("name") or "").strip()
    if not name:
        raise AppError("Name is required.", code="invalid")
    row = City(state=state, name=name)
    _save(row)
    _audit(actor, facility, "masters.city.create", row, request)
    return {"id": str(row.id), "name": row.name}


def list_areas():
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "city": r.city,
            "state": r.state,
            "country": r.country,
            "city_id": str(r.city_ref_id) if r.city_ref_id else "",
        }
        for r in Area.objects.select_related("city_ref")
    ]


def create_area(actor, facility, data, request=None):
    try:
        city = City.objects.select_related("state", "state__country").get(id=data.get("city_id"))
    except City.DoesNotExist as exc:
        raise AppError("City not found.", code="not_found") from exc
    name = (data.get("name") or "").strip()
    if not name:
        raise AppError("Area name is required.", code="invalid")
    row = Area(
        name=name,
        city_ref=city,
        city=city.name,
        state=city.state.name,
        country=city.state.country.name,
    )
    _save(row)
    _audit(actor, facility, "masters.area.create", row, request)
    return {"id": str(row.id), "name": row.name, "city": row.city, "state": row.state}
