from decimal import Decimal

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from apps.billing.models import Bill
from apps.masters.models import Doctor
from apps.patients.models import Patient


def _login(username="receptionist"):
    client = APIClient()
    res = client.post(
        "/api/v1/auth/login",
        {"username": username, "password": settings.DEMO_SEED_PASSWORD},
        format="json",
    )
    assert res.status_code == 200, res.data
    return client


@pytest.mark.django_db
def test_register_posts_fee_and_uhid(seeded_db, settings):
    client = _login()
    res = client.post(
        "/api/v1/patients/register",
        {"first_name": "Anita", "last_name": "Rao", "gender": "F", "mobile": "9811111111", "age_years": 32},
        format="json",
    )
    assert res.status_code == 201, res.data
    assert res.data["uhid"].startswith("DHG/MR/")
    bill = res.data["registration"]["bill"]
    assert bill["net_amount"] == "100.00"
    assert bill["paid_amount"] == "100.00"
    assert bill["status"] == "PAID"
    assert bill["receipts"][0]["receipt_no"]
    patient = Patient.objects.get(uhid=res.data["uhid"])
    assert patient.organization.code == "DHG"


@pytest.mark.django_db
def test_duplicate_mobile_requires_confirmation(seeded_db, settings):
    client = _login()
    body = {"first_name": "Anita", "gender": "F", "mobile": "9811111111", "age_years": 32}
    assert client.post("/api/v1/patients/register", body, format="json").status_code == 201
    again = client.post("/api/v1/patients/register", {**body, "first_name": "Anitha"}, format="json")
    assert again.status_code == 400
    assert again.data["code"] == "possible_duplicate"
    confirmed = client.post(
        "/api/v1/patients/register",
        {**body, "first_name": "Anitha", "confirm_duplicate": True},
        format="json",
    )
    assert confirmed.status_code == 201
    assert confirmed.data["uhid"] != Patient.objects.get(first_name="Anita").uhid


@pytest.mark.django_db
def test_search_by_mobile_and_abha(seeded_db, settings):
    client = _login()
    created = client.post(
        "/api/v1/patients/register",
        {
            "first_name": "Kiran",
            "gender": "M",
            "mobile": "9822222222",
            "abha_id": "12-3456-7890-1234",
            "age_years": 40,
        },
        format="json",
    )
    assert created.status_code == 201
    by_mobile = client.get("/api/v1/patients/search", {"q": "9822222222"})
    by_abha = client.get("/api/v1/patients/search", {"q": "12-3456"})
    assert by_mobile.data[0]["uhid"] == created.data["uhid"]
    assert by_abha.data[0]["abha_id"] == "12-3456-7890-1234"


@pytest.mark.django_db
def test_consultation_discount_limit_and_share(seeded_db, settings):
    client = _login()
    patient = client.post(
        "/api/v1/patients/register",
        {"first_name": "Meera", "gender": "F", "mobile": "9833333333", "age_years": 28},
        format="json",
    ).data
    doctor = Doctor.objects.get(code="DIVYA")
    over = client.post(
        "/api/v1/opd/consultations",
        {
            "patient_id": patient["id"],
            "doctor_id": str(doctor.id),
            "discount_type": "PERCENT",
            "discount_value": "10",
            "paid_amount": "450.00",
        },
        format="json",
    )
    assert over.status_code == 400
    assert over.data["code"] == "discount_not_authorized"

    ok = client.post(
        "/api/v1/opd/consultations",
        {
            "patient_id": patient["id"],
            "doctor_id": str(doctor.id),
            "discount_type": "PERCENT",
            "discount_value": "5",
            "paid_amount": "475.00",
            "weight_kg": "62.5",
            "bp_systolic": 120,
            "bp_diastolic": 80,
        },
        format="json",
    )
    assert ok.status_code == 201, ok.data
    bill = ok.data["bill"]
    assert bill["gross_amount"] == "500.00"
    assert bill["discount_amount"] == "25.00"
    assert bill["net_amount"] == "475.00"
    stored = Bill.objects.get(bill_no=bill["bill_no"])
    assert stored.discount_from_hospital == Decimal("25.00")
    assert stored.discount_from_doctor == Decimal("0.00")

    review = client.post(
        "/api/v1/opd/consultations",
        {"patient_id": patient["id"], "doctor_id": str(doctor.id)},
        format="json",
    )
    assert review.status_code == 201, review.data
    assert review.data["fee_waived_reason"] == "free_review"
    assert review.data["bill"] is None


@pytest.mark.django_db
def test_walk_in_token_and_cashier_cannot_register(seeded_db, settings):
    receptionist = _login()
    patient = receptionist.post(
        "/api/v1/patients/register",
        {"first_name": "Ravi", "gender": "M", "mobile": "9844444444", "age_years": 50},
        format="json",
    ).data
    doctor = Doctor.objects.get(code="DIVYA")
    first = receptionist.post(
        "/api/v1/opd/appointments",
        {"patient_id": patient["id"], "doctor_id": str(doctor.id), "source": "WALKIN"},
        format="json",
    )
    second = receptionist.post(
        "/api/v1/opd/appointments",
        {"patient_id": patient["id"], "doctor_id": str(doctor.id), "source": "ONLINE"},
        format="json",
    )
    assert first.data["token"] == 1
    assert second.data["token"] == 2
    assert second.data["reminder_status"] == "NOT_CONFIGURED"
    cashier = _login("cashier")
    denied = cashier.post(
        "/api/v1/patients/register",
        {"first_name": "Nope", "gender": "M", "mobile": "9800000000", "age_years": 20},
        format="json",
    )
    assert denied.status_code == 403


@pytest.mark.django_db
def test_repeat_register_with_same_idempotency_key(seeded_db, settings):
    client = _login()
    body = {"first_name": "Lata", "gender": "F", "mobile": "9855555555", "age_years": 44}
    first = client.post(
        "/api/v1/patients/register", body, format="json", HTTP_IDEMPOTENCY_KEY="reg-lata-1"
    )
    second = client.post(
        "/api/v1/patients/register", body, format="json", HTTP_IDEMPOTENCY_KEY="reg-lata-1"
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.data["uhid"] == second.data["uhid"]
    assert Patient.objects.filter(mobile="9855555555").count() == 1
