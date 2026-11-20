import pytest
from django.conf import settings
from rest_framework.test import APIClient

from apps.masters.models import Procedure


def _login(username):
    client = APIClient()
    res = client.post(
        "/api/v1/auth/login",
        {"username": username, "password": settings.DEMO_SEED_PASSWORD},
        format="json",
    )
    assert res.status_code == 200, res.data
    return client


@pytest.mark.django_db
def test_doctor_cannot_edit_masters(seeded_db):
    client = _login("doctor")
    res = client.post("/api/v1/masters/departments", {"name": "ENT"}, format="json")
    assert res.status_code == 403
    assert res.data["code"] == "permission_denied"


@pytest.mark.django_db
def test_department_is_unique_per_facility(seeded_db):
    client = _login("facadmin")
    first = client.post("/api/v1/masters/departments", {"name": "ENT"}, format="json")
    assert first.status_code == 201, first.data
    again = client.post("/api/v1/masters/departments", {"name": "ENT"}, format="json")
    assert again.status_code == 409
    assert again.data["code"] == "duplicate"


@pytest.mark.django_db
def test_procedure_shares_must_sum_to_amount(seeded_db):
    client = _login("facadmin")
    res = client.post(
        "/api/v1/masters/procedures",
        {
            "code": "SUT",
            "name": "Suturing",
            "amount": "300.00",
            "hospital_share": "100.00",
            "doctor_share": "100.00",
        },
        format="json",
    )
    assert res.status_code == 400
    assert res.data["code"] == "bad_shares"


@pytest.mark.django_db
def test_percent_adjust_and_copy_to_organization(seeded_db):
    client = _login("facadmin")
    adjusted = client.post(
        "/api/v1/masters/tariffs/adjust",
        {"percent": "10.00", "direction": "UP", "kind": "PROCEDURE"},
        format="json",
    )
    assert adjusted.status_code == 200, adjusted.data
    dressing = Procedure.objects.get(code="DRESS")
    assert dressing.amount == 220
    assert dressing.hospital_share == 220
    assert dressing.doctor_share == 0

    catalog = client.get("/api/v1/masters")
    party = next(row for row in catalog.data["parties"] if row["name"] == "Demo TPA")
    copied = client.post("/api/v1/masters/tariffs/copy", {"party_id": party["id"]}, format="json")
    assert copied.status_code == 200, copied.data
    assert copied.data["copied"] >= 1
    again = client.get("/api/v1/masters")
    match = [
        row
        for row in again.data["tariffs"]
        if row["party"] == "Demo TPA" and row["procedure"] == "Dressing"
    ]
    assert match
    assert match[0]["amount"] == "220.00"


@pytest.mark.django_db
def test_inactive_payment_mode_cannot_collect(seeded_db):
    admin = _login("facadmin")
    catalog = admin.get("/api/v1/masters")
    upi = next(row for row in catalog.data["payment_modes"] if row["code"] == "UPI")
    patched = admin.patch(f"/api/v1/masters/payment-modes/{upi['id']}", {"is_active": False}, format="json")
    assert patched.status_code == 200

    cashier = _login("cashier")
    patient = cashier.post(
        "/api/v1/patients/register",
        {"first_name": "Mode", "gender": "M", "mobile": "9811190001", "age_years": 30},
        format="json",
    )
    if patient.status_code == 403:
        desk = _login("receptionist")
        patient = desk.post(
            "/api/v1/patients/register",
            {"first_name": "Mode", "gender": "M", "mobile": "9811190001", "age_years": 30},
            format="json",
        )
    bill = cashier.post(
        "/api/v1/billing/charges",
        {
            "patient_id": patient.data["id"],
            "description": "Mode check",
            "amount": "50.00",
            "hospital_share": "50.00",
            "doctor_share": "0.00",
            "paid_amount": "0.00",
        },
        format="json",
    )
    assert bill.status_code == 201, bill.data
    collected = cashier.post(
        "/api/v1/billing/collect",
        {"bill_id": bill.data["id"], "amount": "50.00", "mode": "UPI"},
        format="json",
    )
    assert collected.status_code == 400
    assert collected.data["code"] == "bad_payment"


@pytest.mark.django_db
def test_discount_rule_is_a_facility_ceiling(seeded_db):
    admin = _login("facadmin")
    catalog = admin.get("/api/v1/masters")
    rule = next(row for row in catalog.data["discount_rules"] if row["name"] == "Facility ceiling")
    patched = admin.patch(
        f"/api/v1/masters/discount-rules/{rule['id']}",
        {"max_percent": "1.00"},
        format="json",
    )
    assert patched.status_code == 200, patched.data

    cashier = _login("cashier")
    patient = _login("receptionist").post(
        "/api/v1/patients/register",
        {"first_name": "Disc", "gender": "F", "mobile": "9811190002", "age_years": 28},
        format="json",
    )
    res = cashier.post(
        "/api/v1/billing/charges",
        {
            "patient_id": patient.data["id"],
            "description": "Discount ceiling",
            "amount": "100.00",
            "hospital_share": "100.00",
            "doctor_share": "0.00",
            "discount_type": "PERCENT",
            "discount_value": "5.00",
            "paid_amount": "0.00",
        },
        format="json",
    )
    assert res.status_code == 400
    assert res.data["code"] == "discount_not_authorized"


@pytest.mark.django_db
def test_ward_bed_and_geography(seeded_db):
    client = _login("facadmin")
    catalog = client.get("/api/v1/masters")
    room_type = next(row for row in catalog.data["room_types"] if row["name"] == "ICU")
    ward = client.post(
        "/api/v1/masters/wards",
        {"name": "ICU 1", "room_type_id": room_type["id"]},
        format="json",
    )
    assert ward.status_code == 201, ward.data
    room = client.post("/api/v1/masters/rooms", {"ward_id": ward.data["id"], "name": "ICU-1"}, format="json")
    assert room.status_code == 201, room.data
    bed = client.post("/api/v1/masters/beds", {"room_id": room.data["id"], "code": "ICU-1A"}, format="json")
    assert bed.status_code == 201, bed.data
    assert bed.data["status"] == "VACANT"

    country = client.post("/api/v1/masters/countries", {"name": "Testland"}, format="json")
    state = client.post(
        "/api/v1/masters/states",
        {"country_id": country.data["id"], "name": "Test State"},
        format="json",
    )
    city = client.post(
        "/api/v1/masters/cities",
        {"state_id": state.data["id"], "name": "Test City"},
        format="json",
    )
    area = client.post(
        "/api/v1/masters/areas",
        {"city_id": city.data["id"], "name": "Test Area"},
        format="json",
    )
    assert area.status_code == 201, area.data
    assert area.data["city"] == "Test City"
    assert area.data["state"] == "Test State"
