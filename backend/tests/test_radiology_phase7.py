from datetime import timedelta
from decimal import Decimal

import pytest
from django.conf import settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.radiology.models import RadiologyConsumable, StudyStatus


def _login(username="radtech"):
    client = APIClient()
    res = client.post(
        "/api/v1/auth/login",
        {"username": username, "password": settings.DEMO_SEED_PASSWORD},
        format="json",
    )
    assert res.status_code == 200, res.data
    return client


def _register_patient(mobile="9811155001"):
    desk = _login("receptionist")
    patient = desk.post(
        "/api/v1/patients/register",
        {
            "first_name": "Rad",
            "last_name": "Patient",
            "gender": "F",
            "mobile": mobile,
            "age_years": 35,
        },
        format="json",
    )
    assert patient.status_code == 201, patient.data
    return patient.data


def _register_cxr(client, patient_id, paid="400.00"):
    catalog = client.get("/api/v1/radiology/catalog")
    assert catalog.status_code == 200, catalog.data
    cxr = next(t for t in catalog.data["tests"] if t["code"] == "CXR")
    order = client.post(
        "/api/v1/radiology/orders",
        {"patient_id": patient_id, "test_ids": [cxr["id"]], "paid_amount": paid},
        format="json",
    )
    assert order.status_code == 201, order.data
    return order.data, cxr, catalog.data


@pytest.mark.django_db
def test_invalid_patient_id_is_not_server_error(seeded_db):
    client = _login()
    catalog = client.get("/api/v1/radiology/catalog")
    cxr = next(t for t in catalog.data["tests"] if t["code"] == "CXR")
    bad = client.post(
        "/api/v1/radiology/orders",
        {"patient_id": "not-a-uuid", "test_ids": [cxr["id"]], "paid_amount": "400.00"},
        format="json",
    )
    assert bad.status_code == 400
    assert bad.data["code"] == "not_found"


@pytest.mark.django_db
def test_lifecycle_schedule_report_pdf_and_consumable(seeded_db):
    client = _login()
    patient = _register_patient()
    order, _cxr, catalog = _register_cxr(client, patient["id"])
    item = order["items"][0]
    assert item["status"] == StudyStatus.REGISTERED
    assert order["bill"]["status"] in ("PAID", "PARTIAL", "DUE")

    when = (timezone.now() + timedelta(hours=1)).isoformat()
    scheduled = client.post(
        f"/api/v1/radiology/items/{item['id']}/schedule",
        {"scheduled_at": when, "slot_label": "Slot A"},
        format="json",
    )
    assert scheduled.status_code == 200, scheduled.data
    assert scheduled.data["status"] == StudyStatus.SCHEDULED

    board = client.get("/api/v1/radiology/schedule-board")
    assert board.status_code == 200
    assert any(row["id"] == item["id"] for row in board.data)

    film_before = RadiologyConsumable.objects.get(name="X-ray film cassette use").quantity_on_hand
    start = client.post(f"/api/v1/radiology/items/{item['id']}/start", {}, format="json")
    assert start.status_code == 200, start.data
    complete = client.post(
        f"/api/v1/radiology/items/{item['id']}/complete",
        {"pacs_url": "https://pacs.example/study/1"},
        format="json",
    )
    assert complete.status_code == 200, complete.data
    assert complete.data["status"] == StudyStatus.COMPLETED
    film_after = RadiologyConsumable.objects.get(name="X-ray film cassette use").quantity_on_hand
    assert film_after == film_before - Decimal("1.000")

    tpl = next(t for t in catalog["templates"] if t["code"] == "CXR_NORMAL")
    rad = _login("radiologist")
    report = rad.post(
        f"/api/v1/radiology/items/{item['id']}/report",
        {
            "template_id": tpl["id"],
            "findings": tpl["findings_template"],
            "impression": tpl["impression_template"],
        },
        format="json",
    )
    assert report.status_code == 200, report.data
    assert report.data["status"] == StudyStatus.REPORTED
    assert report.data["report"]["version"] == 1

    auth = rad.post(f"/api/v1/radiology/items/{item['id']}/authorize", {}, format="json")
    assert auth.status_code == 200, auth.data
    dispatch = rad.post(f"/api/v1/radiology/items/{item['id']}/dispatch", {}, format="json")
    assert dispatch.status_code == 200, dispatch.data
    assert dispatch.data["status"] == StudyStatus.DISPATCHED

    pdf = rad.get(f"/api/v1/radiology/orders/{order['id']}/pdf")
    assert pdf.status_code == 200
    assert pdf["Content-Type"] == "application/pdf"
    assert pdf.content[:4] == b"%PDF"


@pytest.mark.django_db
def test_amend_cancel_and_doctor_denied_register(seeded_db):
    client = _login()
    patient = _register_patient("9811155002")
    order, _cxr, catalog = _register_cxr(client, patient["id"])
    item = order["items"][0]
    when = (timezone.now() + timedelta(hours=2)).isoformat()
    assert (
        client.post(
            f"/api/v1/radiology/items/{item['id']}/schedule",
            {"scheduled_at": when, "slot_label": "B"},
            format="json",
        ).status_code
        == 200
    )
    assert client.post(f"/api/v1/radiology/items/{item['id']}/complete", {}, format="json").status_code == 200

    tpl = next(t for t in catalog["templates"] if t["code"] == "CXR_NORMAL")
    rad = _login("radiologist")
    assert (
        rad.post(
            f"/api/v1/radiology/items/{item['id']}/report",
            {"findings": "Initial", "impression": "Normal"},
            format="json",
        ).status_code
        == 200
    )
    assert rad.post(f"/api/v1/radiology/items/{item['id']}/authorize", {}, format="json").status_code == 200

    amend = rad.post(
        f"/api/v1/radiology/items/{item['id']}/report",
        {
            "findings": "Amended findings",
            "impression": "Still normal",
            "amendment_reason": "Typo fix",
            "template_id": tpl["id"],
        },
        format="json",
    )
    assert amend.status_code == 200, amend.data
    assert amend.data["status"] == StudyStatus.REPORTED
    assert amend.data["report"]["version"] == 2
    assert amend.data["report"]["amendment_reason"] == "Typo fix"

    order2, cxr, _ = _register_cxr(client, patient["id"], paid="0")
    cancel = client.post(
        f"/api/v1/radiology/items/{order2['items'][0]['id']}/cancel",
        {"reason": "Patient left"},
        format="json",
    )
    assert cancel.status_code == 200
    assert cancel.data["status"] == StudyStatus.CANCELLED

    doctor = _login("doctor")
    denied = doctor.post(
        "/api/v1/radiology/orders",
        {"patient_id": patient["id"], "test_ids": [cxr["id"]], "paid_amount": "0"},
        format="json",
    )
    assert denied.status_code == 403

    gel = RadiologyConsumable.objects.get(name="USG gel")
    adj = client.post(
        "/api/v1/radiology/consumables/adjust",
        {"consumable_id": str(gel.id), "kind": "BREAKAGE", "delta": "-10", "remarks": "Spill"},
        format="json",
    )
    assert adj.status_code == 200, adj.data


@pytest.mark.django_db
def test_clinical_order_link_and_idempotent_register(seeded_db):
    from apps.clinical.models import ClinicalOrder
    from apps.opd.models import Visit

    desk = _login("receptionist")
    patient = desk.post(
        "/api/v1/patients/register",
        {"first_name": "LinkRad", "gender": "M", "mobile": "9811155003", "age_years": 42},
        format="json",
    )
    assert patient.status_code == 201, patient.data
    lookups = desk.get("/api/v1/opd/lookups")
    doctor_id = lookups.data["doctors"][0]["id"]
    consult = desk.post(
        "/api/v1/opd/consultations",
        {
            "patient_id": patient.data["id"],
            "doctor_id": doctor_id,
            "weight_kg": "70",
            "bp_systolic": "120",
            "bp_diastolic": "80",
            "paid_amount": "500.00",
        },
        format="json",
    )
    assert consult.status_code == 201, consult.data
    visit = Visit.objects.get(visit_no=consult.data["visit_no"])

    doc = _login("doctor")
    clinical = doc.post(
        "/api/v1/clinical/orders",
        {"visit_id": str(visit.id), "kind": "RADIOLOGY", "code": "CXR", "name": "Chest X-ray PA"},
        format="json",
    )
    assert clinical.status_code == 201, clinical.data

    client = _login()
    order = client.post(
        "/api/v1/radiology/orders",
        {
            "clinical_order_id": clinical.data["id"],
            "paid_amount": "400.00",
            "idempotency_key": "rad-clinical-1",
        },
        format="json",
    )
    assert order.status_code == 201, order.data
    assert order.data["clinical_order_id"] == clinical.data["id"]
    assert order.data["items"][0]["test_code"] == "CXR"

    repeat = client.post(
        "/api/v1/radiology/orders",
        {
            "clinical_order_id": clinical.data["id"],
            "paid_amount": "400.00",
            "idempotency_key": "rad-clinical-1",
        },
        format="json",
    )
    assert repeat.status_code == 201
    assert repeat.data["id"] == order.data["id"]

    item = order.data["items"][0]
    when = (timezone.now() + timedelta(hours=3)).isoformat()
    assert (
        client.post(
            f"/api/v1/radiology/items/{item['id']}/schedule",
            {"scheduled_at": when},
            format="json",
        ).status_code
        == 200
    )
    co = ClinicalOrder.objects.get(id=clinical.data["id"])
    assert co.status == "IN_PROGRESS"
