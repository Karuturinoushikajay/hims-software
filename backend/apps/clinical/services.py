"""Clinical EMR rules. Views validate shape; this module owns alerts and audit."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.accounts.permissions import require_permission
from apps.audit.services import record_audit
from apps.clinical.models import (
    Allergy,
    ClinicalAttachment,
    ClinicalNote,
    ClinicalOrder,
    Diagnosis,
    Drug,
    DrugInteraction,
    FollowUp,
    IcdCode,
    Prescription,
    PrescriptionItem,
)
from apps.common.exceptions import AppError
from apps.masters.models import DocumentTemplate
from apps.opd.models import Visit
from apps.patients.models import Patient


def _facility(request_or_facility):
    return request_or_facility


def _visit(facility, visit_id) -> Visit:
    try:
        return Visit.objects.select_related("patient", "doctor").get(id=visit_id, facility=facility)
    except Visit.DoesNotExist as exc:
        raise AppError("Visit not found in this facility.", code="not_found") from exc


def _patient(facility, patient_id) -> Patient:
    try:
        return Patient.objects.get(id=patient_id, organization=facility.organization)
    except Patient.DoesNotExist as exc:
        raise AppError("Patient not found.", code="not_found") from exc


def note_payload(note: ClinicalNote) -> dict:
    visit = note.visit
    return {
        "id": str(note.id),
        "visit_id": str(visit.id),
        "visit_no": visit.visit_no,
        "patient_id": str(visit.patient_id),
        "doctor_id": str(note.doctor_id),
        "doctor": note.doctor.name,
        "complaints": note.complaints,
        "history": note.history,
        "examination": note.examination,
        "advice": note.advice,
        "diagnoses": [
            {
                "id": str(d.id),
                "name": d.name,
                "icd_code": d.icd_code.code if d.icd_code_id else "",
                "icd_name": d.icd_code.name if d.icd_code_id else "",
                "is_primary": d.is_primary,
            }
            for d in visit.diagnoses.select_related("icd_code")
        ],
        "updated_at": note.updated_at.isoformat(),
    }


def prescription_payload(rx: Prescription) -> dict:
    return {
        "id": str(rx.id),
        "visit_id": str(rx.visit_id),
        "visit_no": rx.visit.visit_no,
        "patient_id": str(rx.visit.patient_id),
        "doctor": rx.doctor.name,
        "notes": rx.notes,
        "allergy_alerts": rx.allergy_alerts,
        "interaction_alerts": rx.interaction_alerts,
        "items": [
            {
                "id": str(item.id),
                "drug_id": str(item.drug_id) if item.drug_id else "",
                "name": item.name,
                "dose": item.dose,
                "frequency": item.frequency,
                "duration_days": item.duration_days,
                "instructions": item.instructions,
            }
            for item in rx.items.all()
        ],
        "created_at": rx.created_at.isoformat(),
    }


@transaction.atomic
def save_clinical_note(*, actor, facility, visit_id, data: dict, request=None) -> ClinicalNote:
    require_permission(actor, facility, "clinical.write")
    visit = _visit(facility, visit_id)
    note, _created = ClinicalNote.objects.update_or_create(
        visit=visit,
        defaults={
            "facility": facility,
            "doctor": visit.doctor,
            "author": actor,
            "complaints": (data.get("complaints") or "").strip(),
            "history": (data.get("history") or "").strip(),
            "examination": (data.get("examination") or "").strip(),
            "advice": (data.get("advice") or "").strip(),
        },
    )
    diagnoses = data.get("diagnoses")
    if diagnoses is not None:
        visit.diagnoses.all().delete()
        for index, row in enumerate(diagnoses):
            icd = None
            name = (row.get("name") or "").strip()
            if row.get("icd_code"):
                try:
                    icd = IcdCode.objects.get(code=row["icd_code"], is_active=True)
                    name = name or icd.name
                except IcdCode.DoesNotExist as exc:
                    raise AppError(f"Unknown ICD code: {row['icd_code']}", code="bad_icd") from exc
            if not name:
                continue
            Diagnosis.objects.create(
                visit=visit,
                icd_code=icd,
                name=name,
                is_primary=bool(row.get("is_primary")) or index == 0,
            )
    record_audit(
        action="clinical.note.save",
        actor=actor,
        facility=facility,
        entity_type="ClinicalNote",
        entity_id=str(note.id),
        after={"visit_no": visit.visit_no},
        request=request,
    )
    return note


def list_allergies(facility, patient_id) -> list[dict]:
    patient = _patient(facility, patient_id)
    return [
        {
            "id": str(row.id),
            "substance": row.substance,
            "drug_id": str(row.drug_id) if row.drug_id else "",
            "reaction": row.reaction,
            "severity": row.severity,
            "is_active": row.is_active,
            "created_at": row.created_at.isoformat(),
        }
        for row in Allergy.objects.filter(patient=patient, is_active=True)
    ]


def record_allergy(*, actor, facility, data: dict, request=None) -> Allergy:
    require_permission(actor, facility, "clinical.write")
    patient = _patient(facility, data.get("patient_id"))
    drug = None
    substance = (data.get("substance") or "").strip()
    if data.get("drug_id"):
        try:
            drug = Drug.objects.get(id=data["drug_id"], facility=facility, is_active=True)
            substance = substance or drug.name
        except Drug.DoesNotExist as exc:
            raise AppError("Drug not found.", code="not_found") from exc
    if not substance:
        raise AppError("Substance is required.", code="invalid")
    severity = data.get("severity") or Allergy.Severity.MODERATE
    if severity not in Allergy.Severity.values:
        raise AppError("Unknown allergy severity.", code="invalid")
    row = Allergy.objects.create(
        patient=patient,
        facility=facility,
        drug=drug,
        substance=substance,
        reaction=(data.get("reaction") or "").strip(),
        severity=severity,
        recorded_by=actor,
    )
    record_audit(
        action="clinical.allergy.record",
        actor=actor,
        facility=facility,
        entity_type="Allergy",
        entity_id=str(row.id),
        after={"substance": substance, "uhid": patient.uhid},
        request=request,
    )
    return row


def _allergy_alerts(patient: Patient, drug_ids: list) -> list[dict]:
    if not drug_ids:
        return []
    rows = Allergy.objects.filter(patient=patient, is_active=True, drug_id__in=drug_ids)
    return [
        {
            "type": "allergy",
            "severity": row.severity,
            "substance": row.substance,
            "message": f"Patient is allergic to {row.substance}.",
        }
        for row in rows
    ]


def _interaction_alerts(facility, drug_ids: list) -> list[dict]:
    if len(drug_ids) < 2:
        return []
    id_set = set(str(d) for d in drug_ids)
    alerts = []
    pairs = DrugInteraction.objects.filter(facility=facility).select_related("drug_a", "drug_b")
    for row in pairs:
        a, b = str(row.drug_a_id), str(row.drug_b_id)
        if a in id_set and b in id_set:
            alerts.append(
                {
                    "type": "interaction",
                    "severity": row.severity,
                    "message": row.message or f"{row.drug_a.name} interacts with {row.drug_b.name}.",
                    "drugs": [row.drug_a.name, row.drug_b.name],
                }
            )
    return alerts


@transaction.atomic
def issue_prescription(*, actor, facility, data: dict, request=None) -> Prescription:
    require_permission(actor, facility, "clinical.write")
    visit = _visit(facility, data.get("visit_id"))
    items = data.get("items") or []
    if not items:
        raise AppError("Add at least one medicine.", code="invalid")
    template = None
    if data.get("template_id"):
        try:
            template = DocumentTemplate.objects.get(
                id=data["template_id"],
                facility=facility,
                kind=DocumentTemplate.Kind.PRESCRIPTION,
                is_active=True,
            )
        except DocumentTemplate.DoesNotExist as exc:
            raise AppError("Prescription template not found.", code="not_found") from exc

    resolved = []
    drug_ids = []
    for index, row in enumerate(items):
        drug = None
        name = (row.get("name") or "").strip()
        if row.get("drug_id"):
            try:
                drug = Drug.objects.get(id=row["drug_id"], facility=facility, is_active=True)
                name = name or drug.name
                drug_ids.append(drug.id)
            except Drug.DoesNotExist as exc:
                raise AppError("Drug not found.", code="not_found") from exc
        if not name:
            raise AppError("Medicine name is required.", code="invalid")
        resolved.append((index, drug, name, row))

    allergy_alerts = _allergy_alerts(visit.patient, drug_ids)
    interaction_alerts = _interaction_alerts(facility, drug_ids)
    if allergy_alerts and not data.get("acknowledge_alerts"):
        raise AppError(
            "Allergy alert: confirm before issuing this prescription.",
            code="allergy_alert",
            fields={"alerts": allergy_alerts + interaction_alerts},
        )
    if interaction_alerts and not data.get("acknowledge_alerts"):
        raise AppError(
            "Drug interaction alert: confirm before issuing this prescription.",
            code="interaction_alert",
            fields={"alerts": allergy_alerts + interaction_alerts},
        )

    rx = Prescription.objects.create(
        visit=visit,
        facility=facility,
        doctor=visit.doctor,
        author=actor,
        template=template,
        notes=(data.get("notes") or (template.body if template else "") or "").strip(),
        allergy_alerts=allergy_alerts,
        interaction_alerts=interaction_alerts,
    )
    for index, drug, name, row in resolved:
        PrescriptionItem.objects.create(
            prescription=rx,
            drug=drug,
            name=name,
            dose=(row.get("dose") or "").strip(),
            frequency=(row.get("frequency") or "").strip(),
            duration_days=row.get("duration_days") or None,
            instructions=(row.get("instructions") or "").strip(),
            sort_order=index,
        )
    record_audit(
        action="clinical.prescription.issue",
        actor=actor,
        facility=facility,
        entity_type="Prescription",
        entity_id=str(rx.id),
        after={
            "visit_no": visit.visit_no,
            "items": len(resolved),
            "alerts": len(allergy_alerts) + len(interaction_alerts),
        },
        request=request,
    )
    return rx


def place_order(*, actor, facility, data: dict, request=None) -> ClinicalOrder:
    require_permission(actor, facility, "clinical.order")
    visit = _visit(facility, data.get("visit_id"))
    kind = data.get("kind")
    if kind not in ClinicalOrder.Kind.values:
        raise AppError("Order kind must be LAB or RADIOLOGY.", code="invalid")
    name = (data.get("name") or "").strip()
    if not name:
        raise AppError("Order name is required.", code="invalid")
    row = ClinicalOrder.objects.create(
        visit=visit,
        facility=facility,
        patient=visit.patient,
        doctor=visit.doctor,
        ordered_by=actor,
        kind=kind,
        code=(data.get("code") or "").strip().upper(),
        name=name,
        notes=(data.get("notes") or "").strip(),
    )
    record_audit(
        action="clinical.order.place",
        actor=actor,
        facility=facility,
        entity_type="ClinicalOrder",
        entity_id=str(row.id),
        after={"kind": kind, "name": name, "visit_no": visit.visit_no},
        request=request,
    )
    return row


def schedule_follow_up(*, actor, facility, data: dict, request=None) -> FollowUp:
    require_permission(actor, facility, "clinical.write")
    visit = _visit(facility, data.get("visit_id"))
    follow_up_on = data.get("follow_up_on")
    if not follow_up_on:
        raise AppError("Follow-up date is required.", code="invalid")
    if hasattr(follow_up_on, "isoformat"):
        on_date = follow_up_on
    else:
        from django.utils.dateparse import parse_date

        on_date = parse_date(str(follow_up_on))
    if not on_date:
        raise AppError("Invalid follow-up date.", code="invalid")
    today = timezone.localdate()
    if on_date < today:
        raise AppError("Follow-up cannot be in the past.", code="invalid")
    row = FollowUp.objects.create(
        visit=visit,
        facility=facility,
        patient=visit.patient,
        doctor=visit.doctor,
        follow_up_on=on_date,
        reason=(data.get("reason") or "").strip(),
        created_by=actor,
    )
    record_audit(
        action="clinical.follow_up.schedule",
        actor=actor,
        facility=facility,
        entity_type="FollowUp",
        entity_id=str(row.id),
        after={"follow_up_on": on_date.isoformat(), "visit_no": visit.visit_no},
        request=request,
    )
    return row


def add_attachment(*, actor, facility, patient_id, visit_id, uploaded_file, description="", request=None):
    require_permission(actor, facility, "clinical.write")
    patient = _patient(facility, patient_id)
    visit = None
    if visit_id:
        visit = _visit(facility, visit_id)
        if visit.patient_id != patient.id:
            raise AppError("Visit does not belong to this patient.", code="invalid")
    if not uploaded_file:
        raise AppError("File is required.", code="invalid")
    row = ClinicalAttachment.objects.create(
        facility=facility,
        patient=patient,
        visit=visit,
        uploaded_by=actor,
        file=uploaded_file,
        description=(description or "").strip(),
        content_type=getattr(uploaded_file, "content_type", "") or "",
    )
    record_audit(
        action="clinical.attachment.add",
        actor=actor,
        facility=facility,
        entity_type="ClinicalAttachment",
        entity_id=str(row.id),
        after={"uhid": patient.uhid, "name": uploaded_file.name},
        request=request,
    )
    return row


def patient_timeline(facility, patient_id) -> dict:
    patient = _patient(facility, patient_id)
    visits = (
        Visit.objects.filter(patient=patient, facility=facility)
        .select_related("doctor", "clinical_note")
        .prefetch_related("diagnoses", "prescriptions__items", "clinical_orders", "follow_ups", "attachments")
        .order_by("-created_at")
    )
    events = []
    for visit in visits:
        events.append(
            {
                "type": "visit",
                "at": visit.created_at.isoformat(),
                "visit_id": str(visit.id),
                "visit_no": visit.visit_no,
                "doctor": visit.doctor.name,
                "fee_waived_reason": visit.fee_waived_reason,
                "vitals": {
                    "weight_kg": str(visit.weight_kg) if visit.weight_kg is not None else "",
                    "bp": (
                        f"{visit.bp_systolic}/{visit.bp_diastolic}"
                        if visit.bp_systolic and visit.bp_diastolic
                        else ""
                    ),
                    "temperature_f": str(visit.temperature_f) if visit.temperature_f is not None else "",
                },
                "note": note_payload(visit.clinical_note) if hasattr(visit, "clinical_note") and visit.clinical_note else None,
                "diagnoses": [
                    {"name": d.name, "icd_code": d.icd_code.code if d.icd_code_id else "", "is_primary": d.is_primary}
                    for d in visit.diagnoses.all()
                ],
                "prescriptions": [prescription_payload(rx) for rx in visit.prescriptions.all()],
                "orders": [
                    {
                        "id": str(o.id),
                        "kind": o.kind,
                        "name": o.name,
                        "status": o.status,
                        "code": o.code,
                    }
                    for o in visit.clinical_orders.all()
                ],
                "follow_ups": [
                    {"id": str(f.id), "follow_up_on": f.follow_up_on.isoformat(), "reason": f.reason}
                    for f in visit.follow_ups.all()
                ],
                "attachments": [
                    {
                        "id": str(a.id),
                        "description": a.description,
                        "url": a.file.url if a.file else "",
                        "content_type": a.content_type,
                    }
                    for a in visit.attachments.all()
                ],
            }
        )
    return {
        "patient": {
            "id": str(patient.id),
            "uhid": patient.uhid,
            "full_name": patient.full_name,
            "medical_history": patient.medical_history,
        },
        "allergies": list_allergies(facility, patient.id),
        "events": events,
    }


def list_drugs(facility) -> list[dict]:
    return [
        {
            "id": str(d.id),
            "code": d.code,
            "name": d.name,
            "generic_name": d.generic_name,
            "schedule": d.schedule,
        }
        for d in Drug.objects.filter(facility=facility, is_active=True)
    ]


def search_icd(query: str) -> list[dict]:
    q = (query or "").strip()
    rows = IcdCode.objects.filter(is_active=True)
    if q:
        rows = rows.filter(models_q_icd(q))[:30]
    else:
        rows = rows[:30]
    return [{"code": r.code, "name": r.name} for r in rows]


def models_q_icd(q: str):
    from django.db.models import Q

    return Q(code__icontains=q) | Q(name__icontains=q)


def list_prescription_templates(facility):
    return [
        {"id": str(t.id), "name": t.name, "body": t.body}
        for t in DocumentTemplate.objects.filter(
            facility=facility, kind=DocumentTemplate.Kind.PRESCRIPTION, is_active=True
        )
    ]
