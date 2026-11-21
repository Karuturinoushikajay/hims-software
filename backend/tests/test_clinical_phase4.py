import pytest
from django.conf import settings
from rest_framework.test import APIClient

from apps.clinical.models import Drug, IcdCode
from apps.opd.models import Visit


def _login(username="doctor"):
    client = APIClient()
    res = client.post(
        "/api/v1/auth/login",
        {"username": username, "password": settings.DEMO_SEED_PASSWORD},
        format="json",
    )
    assert res.status_code == 200, res.data
    return client


def _visit(client):
    desk = _login("receptionist")
    patient = desk.post(
        "/api/v1/patients/register",
        {"first_name": "Clinical", "gender": "F", "mobile": "9811188001", "age_years": 35},
        format="json",
    )
    assert patient.status_code == 201, patient.data
    lookups = desk.get("/api/v1/opd/lookups")
    doctor_id = lookups.data["doctors"][0]["id"]
    consult = client.post(
        "/api/v1/opd/consultations",
        {
            "patient_id": patient.data["id"],
            "doctor_id": doctor_id,
            "weight_kg": "62",
            "bp_systolic": "120",
            "bp_diastolic": "80",
            "paid_amount": "500.00",
        },
        format="json",
    )
    if consult.status_code == 403:
        consult = desk.post(
            "/api/v1/opd/consultations",
            {
                "patient_id": patient.data["id"],
                "doctor_id": doctor_id,
                "weight_kg": "62",
                "bp_systolic": "120",
                "bp_diastolic": "80",
                "paid_amount": "500.00",
            },
            format="json",
        )
    assert consult.status_code == 201, consult.data
    visit = Visit.objects.get(visit_no=consult.data["visit_no"])
    return patient.data["id"], str(visit.id), doctor_id


@pytest.mark.django_db
def test_save_note_with_icd_diagnosis(seeded_db):
    client = _login()
    patient_id, visit_id, _doctor_id = _visit(client)
    note = client.put(
        f"/api/v1/clinical/visits/{visit_id}/note",
        {
            "complaints": "Fever and cough for 2 days",
            "history": "No chronic illness",
            "examination": "Throat congested",
            "advice": "Rest and fluids",
            "diagnoses": [{"icd_code": "J06.9", "name": "", "is_primary": True}],
        },
        format="json",
    )
    assert note.status_code == 200, note.data
    assert note.data["complaints"].startswith("Fever")
    assert note.data["diagnoses"][0]["icd_code"] == "J06.9"
    assert "upper respiratory" in note.data["diagnoses"][0]["name"].lower()

    timeline = client.get(f"/api/v1/clinical/patients/{patient_id}/timeline")
    assert timeline.status_code == 200
    assert timeline.data["events"][0]["visit_no"]
    assert timeline.data["events"][0]["note"]["advice"] == "Rest and fluids"

    pdf = client.get(f"/api/v1/clinical/visits/{visit_id}/summary.pdf")
    assert pdf.status_code == 200
    assert pdf["Content-Type"] == "application/pdf"
    assert pdf.content[:4] == b"%PDF"


@pytest.mark.django_db
def test_allergy_blocks_prescription_until_acknowledged(seeded_db):
    client = _login()
    patient_id, visit_id, _doctor_id = _visit(client)
    amox = Drug.objects.get(code="AMOX500")
    allergy = client.post(
        "/api/v1/clinical/allergies",
        {
            "patient_id": patient_id,
            "drug_id": str(amox.id),
            "reaction": "Rash",
            "severity": "SEVERE",
        },
        format="json",
    )
    assert allergy.status_code == 201, allergy.data

    blocked = client.post(
        "/api/v1/clinical/prescriptions",
        {
            "visit_id": visit_id,
            "items": [{"drug_id": str(amox.id), "dose": "1 cap", "frequency": "TDS", "duration_days": 5}],
        },
        format="json",
    )
    assert blocked.status_code == 400
    assert blocked.data["code"] == "allergy_alert"

    issued = client.post(
        "/api/v1/clinical/prescriptions",
        {
            "visit_id": visit_id,
            "acknowledge_alerts": True,
            "items": [{"drug_id": str(amox.id), "dose": "1 cap", "frequency": "TDS", "duration_days": 5}],
            "notes": "Use only if benefit outweighs risk",
        },
        format="json",
    )
    assert issued.status_code == 201, issued.data
    assert issued.data["allergy_alerts"]
    pdf = client.get(f"/api/v1/clinical/prescriptions/{issued.data['id']}.pdf")
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"


@pytest.mark.django_db
def test_interaction_alert_on_combined_drugs(seeded_db):
    client = _login()
    _patient_id, visit_id, _doctor_id = _visit(client)
    para = Drug.objects.get(code="PARA500")
    ibu = Drug.objects.get(code="IBU400")
    blocked = client.post(
        "/api/v1/clinical/prescriptions",
        {
            "visit_id": visit_id,
            "items": [
                {"drug_id": str(para.id), "dose": "1 tab", "frequency": "TDS", "duration_days": 3},
                {"drug_id": str(ibu.id), "dose": "1 tab", "frequency": "BD", "duration_days": 3},
            ],
        },
        format="json",
    )
    assert blocked.status_code == 400
    assert blocked.data["code"] == "interaction_alert"


@pytest.mark.django_db
def test_lab_order_follow_up_and_cashier_denied_write(seeded_db):
    client = _login()
    patient_id, visit_id, _doctor_id = _visit(client)
    order = client.post(
        "/api/v1/clinical/orders",
        {"visit_id": visit_id, "kind": "LAB", "code": "CBC", "name": "Complete blood count"},
        format="json",
    )
    assert order.status_code == 201, order.data
    assert order.data["status"] == "ORDERED"

    follow = client.post(
        "/api/v1/clinical/follow-ups",
        {"visit_id": visit_id, "follow_up_on": "2099-01-15", "reason": "Review vitals"},
        format="json",
    )
    assert follow.status_code == 201, follow.data

    timeline = client.get(f"/api/v1/clinical/patients/{patient_id}/timeline")
    event = timeline.data["events"][0]
    assert event["orders"][0]["name"] == "Complete blood count"
    assert event["follow_ups"][0]["reason"] == "Review vitals"

    cashier = _login("cashier")
    denied = cashier.put(
        f"/api/v1/clinical/visits/{visit_id}/note",
        {"complaints": "should fail"},
        format="json",
    )
    assert denied.status_code == 403

    assert IcdCode.objects.filter(code="I10").exists()
