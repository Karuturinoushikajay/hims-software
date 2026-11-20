from __future__ import annotations

from datetime import timedelta

from django.db import transaction

from apps.accounts.permissions import require_permission
from apps.audit.services import record_audit
from apps.billing.models import DiscountType, PaymentMode
from apps.billing.services import ChargeLine, bill_payload, facility_today, post_bill
from apps.common.exceptions import AppError
from apps.common.money import money
from apps.masters.models import Doctor, Procedure
from apps.numbering.models import DocumentType
from apps.numbering.services import allocate
from apps.opd.models import Appointment, ProcedureOrder, Reminder, TokenCounter, Visit
from apps.patients.models import Patient


def _next_token(doctor, service_date) -> int:
    counter, _ = TokenCounter.objects.select_for_update().get_or_create(
        doctor=doctor, service_date=service_date, defaults={"next_token": 1}
    )
    token = counter.next_token
    counter.next_token = token + 1
    counter.save(update_fields=["next_token", "updated_at"])
    return token


def free_review_applies(patient: Patient, doctor: Doctor, on_date) -> bool:
    window_start = on_date - timedelta(days=doctor.review_days)
    return Visit.objects.filter(
        patient=patient,
        doctor=doctor,
        fee_waived_reason="",
        bill__isnull=False,
        created_at__date__gte=window_start,
        created_at__date__lte=on_date,
    ).exists()


@transaction.atomic
def book_appointment(*, actor, facility, patient, doctor, source: str, on_date=None) -> Appointment:
    require_permission(actor, facility, "opd.appointment.manage")
    if doctor.facility_id != facility.id:
        raise AppError("Doctor is not at this facility.", code="bad_doctor")
    on_date = on_date or facility_today(facility)
    status = Appointment.Status.CHECKED_IN if source == Appointment.Source.WALKIN else Appointment.Status.BOOKED
    appointment = Appointment.objects.create(
        facility=facility,
        patient=patient,
        doctor=doctor,
        service_date=on_date,
        token=_next_token(doctor, on_date),
        source=source,
        status=status,
    )
    Reminder.objects.create(appointment=appointment)
    record_audit(
        action="opd.appointment",
        actor=actor,
        facility=facility,
        entity_type="Appointment",
        entity_id=str(appointment.id),
        after={"token": appointment.token, "uhid": patient.uhid, "doctor": doctor.name},
    )
    return appointment


@transaction.atomic
def create_consultation(*, actor, facility, data: dict, idempotency_key: str = "") -> dict:
    require_permission(actor, facility, "opd.consult.create")
    patient = Patient.objects.get(id=data["patient_id"], organization=facility.organization)
    doctor = Doctor.objects.get(id=data["doctor_id"], facility=facility, is_active=True)
    on_date = facility_today(facility)
    appointment = None
    if data.get("appointment_id"):
        appointment = Appointment.objects.get(id=data["appointment_id"], facility=facility)

    visit_no = allocate(document_type=DocumentType.VISIT, facility=facility, on_date=on_date)
    waived = free_review_applies(patient, doctor, on_date)
    fee = money(0) if waived else money(doctor.consultation_fee)
    bill = None
    if fee > 0:
        bill = post_bill(
            facility=facility,
            patient=patient,
            actor=actor,
            lines=[
                ChargeLine(
                    source_type="consultation",
                    source_id=visit_no,
                    description=f"Consultation — {doctor.name}",
                    amount=fee,
                    hospital_share=money(doctor.hospital_share),
                    doctor_share=money(doctor.doctor_share),
                )
            ],
            discount_type=data.get("discount_type") or DiscountType.NONE,
            discount_value=data.get("discount_value") or 0,
            paid=data.get("paid_amount"),
            payment_mode=data.get("payment_mode") or PaymentMode.CASH,
            idempotency_key=idempotency_key,
        )
    elif money(doctor.hospital_share) + money(doctor.doctor_share) != money(doctor.consultation_fee) and not waived:
        raise AppError("Doctor fee shares do not match the consultation fee.", code="bad_share")

    if not waived and money(doctor.hospital_share) + money(doctor.doctor_share) != fee:
        raise AppError("Doctor fee shares do not match the consultation fee.", code="bad_share")

    visit = Visit.objects.create(
        facility=facility,
        patient=patient,
        appointment=appointment,
        visit_no=visit_no,
        doctor=doctor,
        patient_type=data.get("patient_type") or Visit.PatientType.DIRECT,
        party_id=data.get("party_id") or None,
        referral_doctor_id=data.get("referral_doctor_id") or None,
        pro_id=data.get("pro_id") or None,
        attendant_relation=data.get("attendant_relation") or "",
        attendant_name=data.get("attendant_name") or "",
        attendant_mobile=data.get("attendant_mobile") or "",
        insurance_covered=bool(data.get("insurance_covered")),
        remarks=data.get("remarks") or "",
        weight_kg=data.get("weight_kg") or None,
        bp_systolic=data.get("bp_systolic") or None,
        bp_diastolic=data.get("bp_diastolic") or None,
        temperature_f=data.get("temperature_f") or None,
        fee_waived_reason="free_review" if waived else "",
        bill=bill,
    )
    if appointment:
        appointment.status = Appointment.Status.DONE
        appointment.save(update_fields=["status", "updated_at"])
    commission_status = None
    if bill:
        from apps.billing.commission import record_commissions

        commission_status = record_commissions(
            bill, referral=visit.referral_doctor, pro=visit.pro
        )
    record_audit(
        action="opd.consult",
        actor=actor,
        facility=facility,
        entity_type="Visit",
        entity_id=str(visit.id),
        after={"visit_no": visit.visit_no, "waived": waived},
    )
    return {
        "visit_no": visit.visit_no,
        "fee_waived_reason": visit.fee_waived_reason,
        "bill": bill_payload(bill) if bill else None,
        "commission_status": commission_status,
    }


@transaction.atomic
def create_procedure_order(*, actor, facility, data: dict, idempotency_key: str = "") -> dict:
    require_permission(actor, facility, "opd.procedure.create")
    patient = Patient.objects.get(id=data["patient_id"], organization=facility.organization)
    procedure = Procedure.objects.get(id=data["procedure_id"], facility=facility, is_active=True)
    if money(procedure.hospital_share) + money(procedure.doctor_share) != money(procedure.amount):
        raise AppError("Procedure shares do not match its amount.", code="bad_share")
    bill = post_bill(
        facility=facility,
        patient=patient,
        actor=actor,
        lines=[
            ChargeLine(
                source_type="procedure",
                source_id=str(procedure.id),
                description=procedure.name,
                amount=money(procedure.amount),
                hospital_share=money(procedure.hospital_share),
                doctor_share=money(procedure.doctor_share),
            )
        ],
        discount_type=data.get("discount_type") or DiscountType.NONE,
        discount_value=data.get("discount_value") or 0,
        paid=data.get("paid_amount"),
        payment_mode=data.get("payment_mode") or PaymentMode.CASH,
        idempotency_key=idempotency_key,
    )
    order = ProcedureOrder.objects.create(
        facility=facility,
        patient=patient,
        procedure=procedure,
        doctor_id=data.get("doctor_id") or None,
        bill=bill,
    )
    record_audit(
        action="opd.procedure",
        actor=actor,
        facility=facility,
        entity_type="ProcedureOrder",
        entity_id=str(order.id),
        after={"procedure": procedure.name, "bill_no": bill.bill_no},
    )
    return {"id": str(order.id), "bill": bill_payload(bill)}


def appointment_payload(row: Appointment) -> dict:
    return {
        "id": str(row.id),
        "token": row.token,
        "status": row.status,
        "source": row.source,
        "service_date": row.service_date.isoformat(),
        "patient_id": str(row.patient_id),
        "patient_name": row.patient.full_name,
        "uhid": row.patient.uhid,
        "mobile": row.patient.mobile,
        "doctor_id": str(row.doctor_id),
        "doctor_name": row.doctor.name,
        "reminder_status": row.reminders.first().status if row.reminders.exists() else "",
    }
