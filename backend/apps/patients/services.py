from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.db.models import Q

from apps.accounts.permissions import require_permission
from apps.audit.services import record_audit
from apps.billing.models import Bill, DiscountType, PaymentMode
from apps.billing.services import ChargeLine, bill_payload, facility_today, post_bill
from apps.common.exceptions import AppError
from apps.common.money import money
from apps.numbering.models import DocumentType
from apps.numbering.services import allocate
from apps.patients.models import Patient, PatientIdentifier, Registration


def _age_from_dob(dob, on_date):
    years = on_date.year - dob.year - ((on_date.month, on_date.day) < (dob.month, dob.day))
    months = (on_date.month - dob.month) % 12
    days = on_date.day - dob.day
    if days < 0:
        months = (months - 1) % 12
        days = 0
    return max(years, 0), months, max(days, 0)


def find_duplicates(organization, *, first_name, last_name, dob, mobile):
    qs = Patient.objects.filter(organization=organization, deleted_at__isnull=True)
    matches = []
    if mobile:
        matches.extend(qs.filter(mobile=mobile)[:5])
    if first_name and last_name and dob:
        named = qs.filter(
            first_name__iexact=first_name.strip(),
            last_name__iexact=last_name.strip(),
            date_of_birth=dob,
        )[:5]
        for row in named:
            if row not in matches:
                matches.append(row)
    return matches


def search_patients(organization, query: str):
    query = (query or "").strip()
    qs = Patient.objects.filter(organization=organization, deleted_at__isnull=True)
    if not query:
        return qs.none()
    return (
        qs.filter(
            Q(uhid__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(mobile__icontains=query)
            | Q(identifiers__kind=PatientIdentifier.Kind.ABHA, identifiers__value__icontains=query)
        )
        .distinct()
        .order_by("first_name", "last_name")[:25]
    )


def patient_payload(patient: Patient, registration: Registration | None = None) -> dict:
    abha = patient.identifiers.filter(kind=PatientIdentifier.Kind.ABHA).first()
    data = {
        "id": str(patient.id),
        "uhid": patient.uhid,
        "full_name": patient.full_name,
        "title": patient.title,
        "first_name": patient.first_name,
        "middle_name": patient.middle_name,
        "last_name": patient.last_name,
        "gender": patient.gender,
        "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
        "age_years": patient.age_years,
        "age_months": patient.age_months,
        "age_days": patient.age_days,
        "blood_group": patient.blood_group,
        "mobile": patient.mobile,
        "address": patient.address,
        "city": patient.city,
        "area": patient.area,
        "abha_id": abha.value if abha else "",
    }
    if registration:
        data["registration"] = {
            "registered_on": registration.registered_on.isoformat(),
            "expires_on": registration.expires_on.isoformat(),
            "bill": bill_payload(registration.bill) if registration.bill_id else None,
        }
    return data


@transaction.atomic
def register_patient(*, actor, facility, data: dict, idempotency_key: str = "") -> dict:
    require_permission(actor, facility, "patients.create")
    if idempotency_key:
        existing = Bill.objects.filter(facility=facility, idempotency_key=idempotency_key).first()
        if existing:
            registration = existing.registrations.order_by("-created_at").first()
            return patient_payload(existing.patient, registration)
    first = (data.get("first_name") or "").strip()
    if not first or not data.get("gender"):
        raise AppError("First name and gender are required.", code="validation_error")
    mobile = (data.get("mobile") or "").strip()
    if not mobile:
        raise AppError("Mobile is required.", code="validation_error", fields={"mobile": ["Required"]})

    on_date = facility_today(facility)
    dob = data.get("date_of_birth")
    if dob:
        years, months, days = _age_from_dob(dob, on_date)
    else:
        years = int(data.get("age_years") or 0)
        months = int(data.get("age_months") or 0)
        days = int(data.get("age_days") or 0)

    duplicates = find_duplicates(
        facility.organization,
        first_name=first,
        last_name=(data.get("last_name") or "").strip(),
        dob=dob,
        mobile=mobile,
    )
    if duplicates and not data.get("confirm_duplicate"):
        raise AppError(
            "A patient with this mobile or name and date of birth already exists.",
            code="possible_duplicate",
            fields={"matches": [patient_payload(p) for p in duplicates]},
        )

    uhid = allocate(document_type=DocumentType.UHID, organization=facility.organization)
    patient = Patient.objects.create(
        organization=facility.organization,
        uhid=uhid,
        title=(data.get("title") or "").strip(),
        first_name=first,
        middle_name=(data.get("middle_name") or "").strip(),
        last_name=(data.get("last_name") or "").strip(),
        gender=data["gender"],
        date_of_birth=dob,
        age_years=years,
        age_months=months,
        age_days=days,
        blood_group=(data.get("blood_group") or "").strip(),
        mobile=mobile,
        landline=(data.get("landline") or "").strip(),
        email=(data.get("email") or "").strip(),
        marital_status=(data.get("marital_status") or "").strip(),
        religion=(data.get("religion") or "").strip(),
        address=(data.get("address") or "").strip(),
        country=(data.get("country") or "India").strip(),
        state=(data.get("state") or "").strip(),
        city=(data.get("city") or "").strip(),
        area=(data.get("area") or "").strip(),
        zip_code=(data.get("zip_code") or "").strip(),
        education=(data.get("education") or "").strip(),
        occupation=(data.get("occupation") or "").strip(),
        birth_mark=(data.get("birth_mark") or "").strip(),
        medical_history=(data.get("medical_history") or "").strip(),
        comments=(data.get("comments") or "").strip(),
        registered_at=facility,
    )
    if data.get("abha_id"):
        PatientIdentifier.objects.create(
            patient=patient, kind=PatientIdentifier.Kind.ABHA, value=data["abha_id"].strip()
        )
    if data.get("id_proof_value"):
        PatientIdentifier.objects.create(
            patient=patient,
            kind=data.get("id_proof_kind") or PatientIdentifier.Kind.OTHER,
            value=data["id_proof_value"].strip(),
        )

    settings_obj = facility.settings
    fee = money(settings_obj.registration_fee)
    bill = None
    if fee > 0:
        bill = post_bill(
            facility=facility,
            patient=patient,
            actor=actor,
            lines=[
                ChargeLine(
                    source_type="registration",
                    source_id=str(patient.id),
                    description="Registration fee",
                    amount=fee,
                    hospital_share=fee,
                    doctor_share=money(0),
                )
            ],
            discount_type=data.get("discount_type") or DiscountType.NONE,
            discount_value=data.get("discount_value") or 0,
            paid=data.get("paid_amount"),
            payment_mode=data.get("payment_mode") or PaymentMode.CASH,
            idempotency_key=idempotency_key,
        )

    registration = Registration.objects.create(
        facility=facility,
        patient=patient,
        registered_on=on_date,
        expires_on=on_date + timedelta(days=settings_obj.registration_validity_days),
        bill=bill,
    )
    record_audit(
        action="patients.register",
        actor=actor,
        facility=facility,
        entity_type="Patient",
        entity_id=str(patient.id),
        after={"uhid": patient.uhid, "name": patient.full_name},
    )
    return patient_payload(patient, registration)
