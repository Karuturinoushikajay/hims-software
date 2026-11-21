from decimal import Decimal

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from apps.laboratory.models import LabReagent, LabResult, SampleStatus


def _login(username="labtech"):
    client = APIClient()
    res = client.post(
        "/api/v1/auth/login",
        {"username": username, "password": settings.DEMO_SEED_PASSWORD},
        format="json",
    )
    assert res.status_code == 200, res.data
    return client


def _register_patient(mobile="9811166001"):
    desk = _login("receptionist")
    patient = desk.post(
        "/api/v1/patients/register",
        {
            "first_name": "Lab",
            "last_name": "Patient",
            "gender": "M",
            "mobile": mobile,
            "age_years": 40,
        },
        format="json",
    )
    assert patient.status_code == 201, patient.data
    return patient.data


def _register_cbc(client, patient_id, paid="350.00"):
    catalog = client.get("/api/v1/laboratory/catalog")
    assert catalog.status_code == 200, catalog.data
    cbc = next(t for t in catalog.data["tests"] if t["code"] == "CBC")
    order = client.post(
        "/api/v1/laboratory/orders",
        {"patient_id": patient_id, "test_ids": [cbc["id"]], "paid_amount": paid},
        format="json",
    )
    assert order.status_code == 201, order.data
    return order.data, cbc


@pytest.mark.django_db
def test_invalid_patient_id_is_not_server_error(seeded_db):
    client = _login()
    catalog = client.get("/api/v1/laboratory/catalog")
    cbc = next(t for t in catalog.data["tests"] if t["code"] == "CBC")
    bad = client.post(
        "/api/v1/laboratory/orders",
        {"patient_id": "ddwa", "test_ids": [cbc["id"]], "paid_amount": "350.00"},
        format="json",
    )
    assert bad.status_code == 400, bad.data
    assert bad.data["code"] == "not_found"


@pytest.mark.django_db
def test_lifecycle_flags_reagent_and_pdf(seeded_db):
    client = _login()
    patient = _register_patient()
    order, cbc = _register_cbc(client, patient["id"])
    item = order["items"][0]
    assert item["status"] == SampleStatus.REGISTERED
    assert item["barcode"]
    assert order["bill"]["status"] in ("PAID", "PARTIAL", "DUE")

    collect = client.post(f"/api/v1/laboratory/items/{item['id']}/collect", {}, format="json")
    assert collect.status_code == 200, collect.data
    receive = client.post(f"/api/v1/laboratory/items/{item['id']}/receive", {}, format="json")
    assert receive.status_code == 200, receive.data

    hb = next(f for f in cbc["fields"] if f["name"] == "Hemoglobin")
    wbc = next(f for f in cbc["fields"] if f["name"] == "WBC")
    before = LabReagent.objects.get(name="CBC Diluent").quantity_on_hand
    results = client.post(
        f"/api/v1/laboratory/items/{item['id']}/results",
        {
            "results": [
                {"field_id": hb["id"], "value_numeric": "6.5"},
                {"field_id": wbc["id"], "value_numeric": "7.0"},
            ]
        },
        format="json",
    )
    assert results.status_code == 200, results.data
    assert results.data["has_critical"] is True
    assert results.data["status"] == SampleStatus.RESULTED
    after = LabReagent.objects.get(name="CBC Diluent").quantity_on_hand
    assert after == before - Decimal("2.000")

    verify = client.post(f"/api/v1/laboratory/items/{item['id']}/verify", {}, format="json")
    assert verify.status_code == 200, verify.data

    path = _login("pathologist")
    auth = path.post(f"/api/v1/laboratory/items/{item['id']}/authorize", {}, format="json")
    assert auth.status_code == 200, auth.data
    dispatch = path.post(f"/api/v1/laboratory/items/{item['id']}/dispatch", {}, format="json")
    assert dispatch.status_code == 200, dispatch.data
    assert dispatch.data["status"] == SampleStatus.DISPATCHED

    pdf = path.get(f"/api/v1/laboratory/orders/{order['id']}/pdf")
    assert pdf.status_code == 200
    assert pdf["Content-Type"] == "application/pdf"
    assert pdf.content[:4] == b"%PDF"

    label = client.get(f"/api/v1/laboratory/items/{item['id']}/barcode")
    assert label.status_code == 200
    assert label.data["barcode"] == item["barcode"]


@pytest.mark.django_db
def test_package_worklist_and_delta_check(seeded_db):
    client = _login()
    patient = _register_patient("9811166002")
    catalog = client.get("/api/v1/laboratory/catalog")
    pkg = next(p for p in catalog.data["packages"] if p["code"] == "HEMOGRAM")
    order = client.post(
        "/api/v1/laboratory/orders",
        {"patient_id": patient["id"], "package_ids": [pkg["id"]], "paid_amount": "450.00"},
        format="json",
    )
    assert order.status_code == 201, order.data
    assert len(order.data["items"]) == 2

    work = client.get("/api/v1/laboratory/worklist?department=HEMATOLOGY")
    assert work.status_code == 200
    assert any(row["lab_no"] == order.data["lab_no"] for row in work.data)

    # First CBC run for delta baseline
    cbc_item = next(i for i in order.data["items"] if i["test_code"] == "CBC")
    cbc = next(t for t in catalog.data["tests"] if t["code"] == "CBC")
    hb = next(f for f in cbc["fields"] if f["name"] == "Hemoglobin")
    wbc = next(f for f in cbc["fields"] if f["name"] == "WBC")
    for path in ("collect", "receive"):
        assert client.post(f"/api/v1/laboratory/items/{cbc_item['id']}/{path}", {}, format="json").status_code == 200
    first = client.post(
        f"/api/v1/laboratory/items/{cbc_item['id']}/results",
        {
            "results": [
                {"field_id": hb["id"], "value_numeric": "14.0"},
                {"field_id": wbc["id"], "value_numeric": "6.0"},
            ]
        },
        format="json",
    )
    assert first.status_code == 200, first.data
    assert client.post(f"/api/v1/laboratory/items/{cbc_item['id']}/verify", {}, format="json").status_code == 200
    path = _login("pathologist")
    assert path.post(f"/api/v1/laboratory/items/{cbc_item['id']}/authorize", {}, format="json").status_code == 200
    assert path.post(f"/api/v1/laboratory/items/{cbc_item['id']}/dispatch", {}, format="json").status_code == 200

    # Second CBC for same patient — large Hb swing triggers delta
    order2, _ = _register_cbc(client, patient["id"])
    item2 = order2["items"][0]
    for step in ("collect", "receive"):
        assert client.post(f"/api/v1/laboratory/items/{item2['id']}/{step}", {}, format="json").status_code == 200
    second = client.post(
        f"/api/v1/laboratory/items/{item2['id']}/results",
        {
            "results": [
                {"field_id": hb["id"], "value_numeric": "10.0"},
                {"field_id": wbc["id"], "value_numeric": "6.5"},
            ]
        },
        format="json",
    )
    assert second.status_code == 200, second.data
    assert second.data["has_delta"] is True
    flags = {r["field"]: r["flag"] for r in second.data["results"]}
    assert flags["Hemoglobin"] in ("DELTA", "LOW")


@pytest.mark.django_db
def test_amendment_cancel_and_doctor_denied_register(seeded_db):
    client = _login()
    patient = _register_patient("9811166003")
    order, cbc = _register_cbc(client, patient["id"])
    item = order["items"][0]
    hb = next(f for f in cbc["fields"] if f["name"] == "Hemoglobin")
    wbc = next(f for f in cbc["fields"] if f["name"] == "WBC")
    for step in ("collect", "receive"):
        assert client.post(f"/api/v1/laboratory/items/{item['id']}/{step}", {}, format="json").status_code == 200
    assert (
        client.post(
            f"/api/v1/laboratory/items/{item['id']}/results",
            {
                "results": [
                    {"field_id": hb["id"], "value_numeric": "13.5"},
                    {"field_id": wbc["id"], "value_numeric": "8.0"},
                ]
            },
            format="json",
        ).status_code
        == 200
    )
    assert client.post(f"/api/v1/laboratory/items/{item['id']}/verify", {}, format="json").status_code == 200
    path = _login("pathologist")
    assert path.post(f"/api/v1/laboratory/items/{item['id']}/authorize", {}, format="json").status_code == 200

    amend = path.post(
        f"/api/v1/laboratory/items/{item['id']}/amend",
        {
            "reason": "Clerical correction",
            "results": [
                {"field_id": hb["id"], "value_numeric": "13.8"},
                {"field_id": wbc["id"], "value_numeric": "8.1"},
            ],
        },
        format="json",
    )
    assert amend.status_code == 200, amend.data
    assert amend.data["status"] == SampleStatus.RESULTED
    current = LabResult.objects.filter(item_id=item["id"], field_id=hb["id"], is_current=True).get()
    assert current.version >= 2
    assert current.amendment_reason == "Clerical correction"

    # Cancel a fresh item
    order2, _ = _register_cbc(client, patient["id"], paid="0")
    item2 = order2["items"][0]
    cancel = client.post(
        f"/api/v1/laboratory/items/{item2['id']}/cancel",
        {"reason": "Patient refused"},
        format="json",
    )
    assert cancel.status_code == 200, cancel.data
    assert cancel.data["status"] == SampleStatus.CANCELLED

    doctor = _login("doctor")
    denied = doctor.post(
        "/api/v1/laboratory/orders",
        {"patient_id": patient["id"], "test_ids": [cbc["id"]], "paid_amount": "0"},
        format="json",
    )
    assert denied.status_code == 403

    # Reagent breakage
    reagent = LabReagent.objects.get(name="CBC Diluent")
    adj = client.post(
        "/api/v1/laboratory/reagents/adjust",
        {"reagent_id": str(reagent.id), "kind": "BREAKAGE", "delta": "-5", "remarks": "Spilled"},
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
        {"first_name": "Link", "gender": "F", "mobile": "9811166004", "age_years": 30},
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
            "weight_kg": "60",
            "bp_systolic": "110",
            "bp_diastolic": "70",
            "paid_amount": "500.00",
        },
        format="json",
    )
    assert consult.status_code == 201, consult.data
    visit = Visit.objects.get(visit_no=consult.data["visit_no"])

    doc = _login("doctor")
    clinical = doc.post(
        "/api/v1/clinical/orders",
        {"visit_id": str(visit.id), "kind": "LAB", "code": "CBC", "name": "Complete blood count"},
        format="json",
    )
    assert clinical.status_code == 201, clinical.data

    client = _login()
    order = client.post(
        "/api/v1/laboratory/orders",
        {
            "clinical_order_id": clinical.data["id"],
            "paid_amount": "350.00",
            "idempotency_key": "lab-clinical-1",
        },
        format="json",
    )
    assert order.status_code == 201, order.data
    assert order.data["clinical_order_id"] == clinical.data["id"]
    assert order.data["items"][0]["test_code"] == "CBC"

    repeat = client.post(
        "/api/v1/laboratory/orders",
        {
            "clinical_order_id": clinical.data["id"],
            "paid_amount": "350.00",
            "idempotency_key": "lab-clinical-1",
        },
        format="json",
    )
    assert repeat.status_code == 201
    assert repeat.data["id"] == order.data["id"]

    item = order.data["items"][0]
    for step in ("collect", "receive"):
        assert client.post(f"/api/v1/laboratory/items/{item['id']}/{step}", {}, format="json").status_code == 200
    co = ClinicalOrder.objects.get(id=clinical.data["id"])
    assert co.status == "IN_PROGRESS"
