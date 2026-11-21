import pytest
from django.conf import settings
from rest_framework.test import APIClient

from apps.ipd.models import AdmissionStatus, IpDailyCharge
from apps.masters.models import Bed, Doctor


def _login(username="receptionist"):
    client = APIClient()
    res = client.post(
        "/api/v1/auth/login",
        {"username": username, "password": settings.DEMO_SEED_PASSWORD},
        format="json",
    )
    assert res.status_code == 200, res.data
    return client


def _patient(client, mobile="9811144001"):
    patient = client.post(
        "/api/v1/patients/register",
        {"first_name": "Inpatient", "gender": "M", "mobile": mobile, "age_years": 45},
        format="json",
    )
    assert patient.status_code == 201, patient.data
    return patient.data


def _admit(client, patient_id, bed_code="101-A", advance="2000.00"):
    doctor = Doctor.objects.filter(is_active=True).first()
    bed = Bed.objects.get(code=bed_code)
    res = client.post(
        "/api/v1/ipd/admissions",
        {
            "patient_id": patient_id,
            "doctor_id": str(doctor.id),
            "bed_id": str(bed.id),
            "advance_amount": advance,
            "is_vip": True,
            "food_preference": "VEG",
            "attendant_name": "Spouse",
            "attendant_mobile": "9000000099",
            "icd_code": "J06.9",
        },
        format="json",
    )
    assert res.status_code == 201, res.data
    return res.data


@pytest.mark.django_db
def test_admit_bed_board_daily_charge_and_transfer(seeded_db):
    client = _login()
    patient = _patient(client)
    admission = _admit(client, patient["id"])
    assert admission["status"] == AdmissionStatus.ADMITTED
    assert admission["is_vip"] is True
    assert IpDailyCharge.objects.filter(admission_id=admission["id"]).exists()

    board = client.get("/api/v1/ipd/bed-board")
    assert board.status_code == 200
    assert board.data["counts"]["OCCUPIED"] >= 1
    occupied = next(b for b in board.data["beds"] if b["admission_id"] == admission["id"])
    assert occupied["status"] == "OCCUPIED"
    assert occupied["flags"]["vip"] is True

    target = Bed.objects.get(code="101-B")
    transfer = client.post(
        f"/api/v1/ipd/admissions/{admission['id']}/transfer-bed",
        {"bed_id": str(target.id), "reason": "Prefer window"},
        format="json",
    )
    assert transfer.status_code == 200, transfer.data
    assert transfer.data["bed_id"] == str(target.id)
    assert Bed.objects.get(code="101-A").status == "VACANT"
    assert Bed.objects.get(code="101-B").status == "OCCUPIED"

    doctors = list(Doctor.objects.filter(is_active=True)[:2])
    if len(doctors) >= 2 and doctors[0].id != Doctor.objects.get(id=admission["doctor_id"]).id:
        other = doctors[1] if str(doctors[0].id) == admission["doctor_id"] else doctors[0]
    else:
        other = Doctor.objects.exclude(id=admission["doctor_id"]).first() or doctors[0]
    if str(other.id) != admission["doctor_id"]:
        doc_xfer = client.post(
            f"/api/v1/ipd/admissions/{admission['id']}/transfer-doctor",
            {"doctor_id": str(other.id), "reason": "On call"},
            format="json",
        )
        assert doc_xfer.status_code == 200, doc_xfer.data


@pytest.mark.django_db
def test_nursing_mar_order_settle_certificate_and_cancel_discharge(seeded_db):
    desk = _login()
    patient = _patient(desk, "9811144002")
    admission = _admit(desk, patient["id"], bed_code="102-A", advance="5000.00")

    nurse = _login("nurse")
    note = nurse.post(
        f"/api/v1/ipd/admissions/{admission['id']}/nursing-notes",
        {
            "note": "Stable overnight",
            "temperature_c": "36.8",
            "pulse": "78",
            "bp_systolic": "120",
            "bp_diastolic": "80",
            "spo2": "98",
            "diet": "Soft diet",
        },
        format="json",
    )
    assert note.status_code == 200, note.data
    assert note.data["diet"] == "Soft diet"
    assert len(note.data["nursing_notes"]) >= 1

    mar = nurse.post(
        f"/api/v1/ipd/admissions/{admission['id']}/mar",
        {"drug_name": "Paracetamol", "dose": "500mg", "route": "PO"},
        format="json",
    )
    assert mar.status_code == 200, mar.data

    doctor = _login("doctor")
    order = doctor.post(
        f"/api/v1/ipd/admissions/{admission['id']}/doctor-orders",
        {"order_text": "Continue IV fluids; monitor BP q4h"},
        format="json",
    )
    assert order.status_code == 200, order.data

    summary = doctor.post(
        f"/api/v1/ipd/admissions/{admission['id']}/discharge-summary",
        {
            "diagnosis": "Acute URI",
            "condition_on_admission": "Fever",
            "condition_on_discharge": "Improved",
            "treatment_given": "Supportive care",
            "treatment_advised": "Rest 3 days",
            "icd_code": "J06.9",
        },
        format="json",
    )
    assert summary.status_code == 200, summary.data

    settle = desk.post(
        f"/api/v1/ipd/admissions/{admission['id']}/settle",
        {},
        format="json",
    )
    assert settle.status_code == 200, settle.data
    assert settle.data["status"] == AdmissionStatus.DISCHARGED
    assert Bed.objects.get(code="102-A").status == "VACANT"
    assert settle.data["settlement"]["days"] >= 1

    pdf = doctor.get(f"/api/v1/ipd/admissions/{admission['id']}/discharge.pdf")
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"

    cert = doctor.post(
        "/api/v1/ipd/certificates",
        {
            "admission_id": admission["id"],
            "kind": "FITNESS",
            "disease_name": "URI",
            "fit_on": "2099-01-01",
            "body": "Fit to resume work.",
        },
        format="json",
    )
    assert cert.status_code == 201, cert.data
    cert_pdf = doctor.get(f"/api/v1/ipd/certificates/{cert.data['id']}/pdf")
    assert cert_pdf.status_code == 200
    assert cert_pdf.content[:4] == b"%PDF"

    reopen = desk.post(
        f"/api/v1/ipd/admissions/{admission['id']}/cancel-discharge",
        {"reason": "Early discharge error"},
        format="json",
    )
    assert reopen.status_code == 200, reopen.data
    assert reopen.data["status"] == AdmissionStatus.ADMITTED
    assert Bed.objects.get(code="102-A").status == "OCCUPIED"


@pytest.mark.django_db
def test_duplicate_active_admission_and_doctor_denied_admit(seeded_db):
    client = _login()
    patient = _patient(client, "9811144003")
    first = _admit(client, patient["id"], bed_code="ICU-1A")
    assert first["status"] == AdmissionStatus.ADMITTED
    second = client.post(
        "/api/v1/ipd/admissions",
        {
            "patient_id": patient["id"],
            "doctor_id": first["doctor_id"],
            "bed_id": str(Bed.objects.get(code="ICU-1B").id),
        },
        format="json",
    )
    assert second.status_code == 400
    assert second.data["code"] == "conflict"

    doctor = _login("doctor")
    denied = doctor.post(
        "/api/v1/ipd/admissions",
        {
            "patient_id": patient["id"],
            "doctor_id": first["doctor_id"],
            "bed_id": str(Bed.objects.get(code="ICU-1B").id),
        },
        format="json",
    )
    assert denied.status_code == 403
