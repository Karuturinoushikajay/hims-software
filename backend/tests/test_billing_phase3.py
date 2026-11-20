from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.billing.models import Bill, CommissionEntry, Payment, TaxCategory
from apps.billing.services import ChargeLine, post_bill, split_gst
from apps.masters.models import Doctor, ReferralDoctor
from apps.organizations.models import Facility
from apps.patients.models import Patient


def _login(username="cashier"):
    client = APIClient()
    res = client.post(
        "/api/v1/auth/login",
        {"username": username, "password": "ChangeMeDemo!2026"},
        format="json",
    )
    assert res.status_code == 200, res.data
    return client


def _patient(client, mobile="9811100001"):
    created = client.post(
        "/api/v1/patients/register",
        {"first_name": "Billing", "gender": "F", "mobile": mobile, "age_years": 40},
        format="json",
    )
    if created.status_code == 403:
        receptionist = _login("receptionist")
        created = receptionist.post(
            "/api/v1/patients/register",
            {"first_name": "Billing", "gender": "F", "mobile": mobile, "age_years": 40},
            format="json",
        )
    assert created.status_code == 201, created.data
    return created.data["id"], created.data["uhid"]


@pytest.mark.django_db
def test_partial_payment_then_due_collection(seeded_db):
    client = _login()
    patient_id, _uhid = _patient(client)
    bill = client.post(
        "/api/v1/billing/charges",
        {
            "patient_id": patient_id,
            "description": "Dressing extra",
            "amount": "100.00",
            "hospital_share": "100.00",
            "doctor_share": "0.00",
            "paid_amount": "40.00",
            "mode": "CASH",
        },
        format="json",
    )
    assert bill.status_code == 201, bill.data
    assert bill.data["status"] == "PARTIALLY_PAID"
    assert bill.data["due_amount"] == "60.00"
    collected = client.post(
        "/api/v1/billing/collect",
        {"bill_id": bill.data["id"], "amount": "60.00", "mode": "UPI"},
        format="json",
    )
    assert collected.status_code == 200, collected.data
    assert collected.data["status"] == "PAID"
    assert collected.data["due_amount"] == "0.00"
    again = client.post(
        "/api/v1/billing/collect",
        {"bill_id": bill.data["id"], "amount": "1.00", "mode": "CASH"},
        format="json",
    )
    assert again.status_code == 400
    assert again.data["code"] == "bad_payment"


@pytest.mark.django_db
def test_collect_is_idempotent(seeded_db):
    client = _login()
    patient_id, _uhid = _patient(client, "9811100002")
    bill = client.post(
        "/api/v1/billing/charges",
        {
            "patient_id": patient_id,
            "description": "Due bill",
            "amount": "80.00",
            "hospital_share": "80.00",
            "doctor_share": "0.00",
            "paid_amount": "0.00",
        },
        format="json",
    )
    assert bill.status_code == 201, bill.data
    body = {"bill_id": bill.data["id"], "amount": "80.00", "mode": "CASH"}
    first = client.post("/api/v1/billing/collect", body, format="json", HTTP_IDEMPOTENCY_KEY="collect-1")
    second = client.post("/api/v1/billing/collect", body, format="json", HTTP_IDEMPOTENCY_KEY="collect-1")
    assert first.status_code == 200 and second.status_code == 200
    assert first.data["paid_amount"] == second.data["paid_amount"] == "80.00"
    assert Payment.objects.filter(bill_id=bill.data["id"]).count() == 1


@pytest.mark.django_db
def test_gst_is_zero_until_confirmed_then_splits_intrastate(seeded_db):
    client = _login()
    patient_id, _uhid = _patient(client, "9811100003")
    category = TaxCategory.objects.get(name="Outpatient services")
    body = {
        "patient_id": patient_id,
        "description": "Procedure package",
        "amount": "100.00",
        "hospital_share": "100.00",
        "doctor_share": "0.00",
        "tax_category_id": str(category.id),
        "paid_amount": "100.00",
    }
    quiet = client.post("/api/v1/billing/charges", body, format="json")
    assert quiet.status_code == 201, quiet.data
    assert quiet.data["gst_applied"] is False
    assert quiet.data["tax_amount"] == "0.00"
    assert quiet.data["net_amount"] == "100.00"

    facility = Facility.objects.get(code="DMSH")
    facility.settings.gstin_confirmed = True
    facility.settings.save(update_fields=["gstin_confirmed"])
    body["paid_amount"] = "118.00"
    taxed = client.post("/api/v1/billing/charges", body, format="json")
    assert taxed.status_code == 201, taxed.data
    assert taxed.data["tax_amount"] == "18.00"
    assert taxed.data["cgst_amount"] == "9.00"
    assert taxed.data["sgst_amount"] == "9.00"
    assert taxed.data["igst_amount"] == "0.00"
    assert taxed.data["net_amount"] == "118.00"

    patient = Patient.objects.get(id=patient_id)
    actor = User.objects.get(username="cashier")
    inter = post_bill(
        facility=facility,
        patient=patient,
        actor=actor,
        lines=[
            ChargeLine("service", "", "Outside state", Decimal("100"), Decimal("100"), Decimal("0"), Decimal("18"))
        ],
        paid=Decimal("118.00"),
        place_of_supply="27",
    )
    assert inter.igst_amount == Decimal("18.00")
    assert inter.cgst_amount == Decimal("0.00")
    assert split_gst(Decimal("1.81"), True) == (Decimal("0.91"), Decimal("0.90"), Decimal("0.00"))


@pytest.mark.django_db
def test_advance_settles_a_due(seeded_db):
    client = _login()
    patient_id, _uhid = _patient(client, "9811100004")
    advance = client.post(
        "/api/v1/billing/advances",
        {"patient_id": patient_id, "amount": "150.00", "mode": "CASH"},
        format="json",
    )
    assert advance.status_code == 201, advance.data
    assert advance.data["advance_no"].startswith("DMSH/ADV/")
    bill = client.post(
        "/api/v1/billing/charges",
        {
            "patient_id": patient_id,
            "description": "Unpaid service",
            "amount": "100.00",
            "hospital_share": "100.00",
            "doctor_share": "0.00",
            "paid_amount": "0.00",
        },
        format="json",
    )
    applied = client.post(
        f"/api/v1/billing/advances/{advance.data['id']}/apply",
        {"bill_id": bill.data["id"], "amount": "100.00"},
        format="json",
    )
    assert applied.status_code == 200, applied.data
    assert applied.data["status"] == "PAID"
    assert applied.data["receipts"][-1]["mode"] == "ADVANCE"
    listed = client.get("/api/v1/billing/advances", {"patient_id": patient_id})
    assert listed.data[0]["balance"] == "50.00"


@pytest.mark.django_db
def test_refund_above_threshold_waits_for_authorization(seeded_db):
    facility = Facility.objects.get(code="DMSH")
    facility.settings.refund_auth_threshold = Decimal("50.00")
    facility.settings.save(update_fields=["refund_auth_threshold"])
    client = _login()
    patient_id, _uhid = _patient(client, "9811100005")
    bill = client.post(
        "/api/v1/billing/charges",
        {
            "patient_id": patient_id,
            "description": "Refundable",
            "amount": "100.00",
            "hospital_share": "100.00",
            "doctor_share": "0.00",
            "paid_amount": "100.00",
        },
        format="json",
    )
    pending = client.post(
        "/api/v1/billing/refunds",
        {"bill_id": bill.data["id"], "amount": "100.00", "mode": "CASH", "reason": "Patient left"},
        format="json",
    )
    assert pending.status_code == 201, pending.data
    assert pending.data["status"] == "PENDING"
    denied = client.post(
        f"/api/v1/billing/refunds/{pending.data['id']}/authorize",
        {"approve": True},
        format="json",
    )
    assert denied.status_code == 403
    admin = _login("facadmin")
    approved = admin.post(
        f"/api/v1/billing/refunds/{pending.data['id']}/authorize",
        {"approve": True},
        format="json",
    )
    assert approved.status_code == 200, approved.data
    assert approved.data["status"] == "POSTED"
    assert approved.data["refund_no"].startswith("DMSH/REF/")
    refreshed = client.get(f"/api/v1/billing/bills/{bill.data['id']}")
    assert refreshed.data["paid_amount"] == "0.00"
    assert refreshed.data["due_amount"] == "100.00"
    assert refreshed.data["status"] == "POSTED"


@pytest.mark.django_db
def test_cancel_credits_the_bill_and_refunds_cash(seeded_db):
    client = _login()
    patient_id, _uhid = _patient(client, "9811100006")
    bill = client.post(
        "/api/v1/billing/charges",
        {
            "patient_id": patient_id,
            "description": "To cancel",
            "amount": "100.00",
            "hospital_share": "100.00",
            "doctor_share": "0.00",
        },
        format="json",
    )
    cancelled = client.post(
        f"/api/v1/billing/bills/{bill.data['id']}/cancel",
        {"reason": "Wrong patient", "mode": "CASH"},
        format="json",
    )
    assert cancelled.status_code == 200, cancelled.data
    assert cancelled.data["credit_note_no"].startswith("DMSH/CN/")
    assert cancelled.data["refund"]["status"] == "POSTED"
    assert cancelled.data["bill"]["status"] == "CANCELLED"
    assert cancelled.data["bill"]["due_amount"] == "0.00"
    extra = client.post(
        "/api/v1/billing/credit-notes",
        {"bill_id": bill.data["id"], "amount": "1.00", "reason": "Again"},
        format="json",
    )
    assert extra.status_code == 400
    assert extra.data["code"] == "bad_credit"
    with pytest.raises(RuntimeError):
        Bill.objects.get(id=bill.data["id"]).save()


@pytest.mark.django_db
def test_day_close_blocks_new_money_and_can_reopen(seeded_db):
    client = _login()
    opened = client.post("/api/v1/billing/shifts", {"opening_cash": "1000.00"}, format="json")
    assert opened.status_code == 201, opened.data
    blocked = client.post("/api/v1/billing/day-close", {}, format="json")
    assert blocked.status_code == 400
    assert blocked.data["code"] == "shift_open"
    closed_shift = client.post("/api/v1/billing/shifts/close", {"counted_cash": "1000.00"}, format="json")
    assert closed_shift.status_code == 200, closed_shift.data
    assert closed_shift.data["variance"] == "0.00"
    patient_id, _uhid = _patient(client, "9811100007")
    closed = client.post("/api/v1/billing/day-close", {}, format="json")
    assert closed.status_code == 200, closed.data
    denied = client.post(
        "/api/v1/billing/charges",
        {
            "patient_id": patient_id,
            "description": "After close",
            "amount": "10.00",
            "hospital_share": "10.00",
            "doctor_share": "0.00",
        },
        format="json",
    )
    assert denied.status_code == 400
    assert denied.data["code"] == "day_closed"
    reopened = client.post("/api/v1/billing/day-close", {"reopen": True}, format="json")
    assert reopened.status_code == 200
    assert reopened.data["reopened"] is True


@pytest.mark.django_db
def test_commission_and_tds_run_only_after_rate_confirmation(seeded_db):
    client = _login("receptionist")
    patient_id, _uhid = _patient(client, "9811100008")
    doctor = Doctor.objects.get(code="DIVYA")
    referral = ReferralDoctor.objects.get(name="City Clinic")
    body = {
        "patient_id": patient_id,
        "doctor_id": str(doctor.id),
        "referral_doctor_id": str(referral.id),
        "payment_mode": "CASH",
    }
    waiting = client.post("/api/v1/opd/consultations", body, format="json")
    assert waiting.status_code == 201, waiting.data
    assert waiting.data["commission_status"] == "NOT_CONFIGURED"
    assert CommissionEntry.objects.count() == 0

    facility = Facility.objects.get(code="DMSH")
    facility.settings.tds_rate_confirmed = True
    facility.settings.save(update_fields=["tds_rate_confirmed"])
    patient_id, _uhid = _patient(client, "9811100009")
    body["patient_id"] = patient_id
    posted = client.post("/api/v1/opd/consultations", body, format="json")
    assert posted.status_code == 201, posted.data
    assert posted.data["commission_status"] == "POSTED"
    entry = CommissionEntry.objects.get(bill__bill_no=posted.data["bill"]["bill_no"])
    assert entry.base_amount == Decimal("300.00")
    assert entry.commission_amount == Decimal("30.00")
    assert entry.tds_amount == Decimal("3.00")
    assert entry.net_payable == Decimal("27.00")


@pytest.mark.django_db
def test_discount_above_limit_posts_only_after_approval(seeded_db):
    client = _login("receptionist")
    patient_id, _uhid = _patient(client, "9811100010")
    doctor = Doctor.objects.get(code="DIVYA")
    body = {
        "patient_id": patient_id,
        "doctor_id": str(doctor.id),
        "discount_type": "PERCENT",
        "discount_value": "8.00",
    }
    denied = client.post("/api/v1/opd/consultations", body, format="json")
    assert denied.status_code == 400
    assert denied.data["code"] == "discount_not_authorized"
    requested = client.post("/api/v1/billing/discount-requests", body, format="json")
    assert requested.status_code == 201, requested.data
    cashier = _login()
    forbidden = cashier.post(
        f"/api/v1/billing/discount-requests/{requested.data['id']}/decide",
        {"approve": True},
        format="json",
    )
    assert forbidden.status_code == 403
    admin = _login("facadmin")
    approved = admin.post(
        f"/api/v1/billing/discount-requests/{requested.data['id']}/decide",
        {"approve": True},
        format="json",
    )
    assert approved.status_code == 200, approved.data
    assert approved.data["status"] == "APPROVED"
    bill = Bill.objects.get(bill_no=approved.data["result_bill_no"])
    assert bill.discount_amount == Decimal("40.00")
    assert bill.net_amount == Decimal("460.00")


@pytest.mark.django_db
def test_invoice_pdf_downloads(seeded_db):
    client = _login()
    patient_id, _uhid = _patient(client, "9811100011")
    bill = client.post(
        "/api/v1/billing/charges",
        {
            "patient_id": patient_id,
            "description": "Print me",
            "amount": "50.00",
            "hospital_share": "50.00",
            "doctor_share": "0.00",
        },
        format="json",
    )
    pdf = client.get(f"/api/v1/billing/bills/{bill.data['id']}/pdf?layout=thermal&doc=receipt")
    assert pdf.status_code == 200
    assert pdf["Content-Type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    doctor = _login("doctor")
    hidden = doctor.get("/api/v1/billing/bills")
    assert hidden.status_code == 403
