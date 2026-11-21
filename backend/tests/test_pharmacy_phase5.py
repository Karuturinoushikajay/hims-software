from datetime import timedelta

import pytest
from django.conf import settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.clinical.models import Drug
from apps.pharmacy.models import ControlledDrugEntry, StockBatch


def _login(username="pharmacist"):
    client = APIClient()
    res = client.post(
        "/api/v1/auth/login",
        {"username": username, "password": settings.DEMO_SEED_PASSWORD},
        format="json",
    )
    assert res.status_code == 200, res.data
    return client


def _receive(client, drug_id, batch_no, expiry, qty, unit_cost="1.00"):
    suppliers = client.get("/api/v1/pharmacy/suppliers")
    assert suppliers.status_code == 200
    supplier_id = suppliers.data[0]["id"]
    grn = client.post(
        "/api/v1/pharmacy/grn",
        {
            "supplier_id": supplier_id,
            "invoice_no": "INV-1",
            "lines": [
                {
                    "drug_id": drug_id,
                    "batch_no": batch_no,
                    "expiry_date": expiry.isoformat(),
                    "quantity": qty,
                    "unit_cost": unit_cost,
                }
            ],
        },
        format="json",
    )
    assert grn.status_code == 201, grn.data
    return grn.data


@pytest.mark.django_db
def test_po_grn_and_fefo_sale(seeded_db):
    client = _login()
    para = Drug.objects.get(code="PARA500")
    suppliers = client.get("/api/v1/pharmacy/suppliers")
    supplier_id = suppliers.data[0]["id"]
    today = timezone.localdate()
    po = client.post(
        "/api/v1/pharmacy/purchase-orders",
        {
            "supplier_id": supplier_id,
            "lines": [{"drug_id": str(para.id), "quantity": 100, "unit_cost": "1.00"}],
        },
        format="json",
    )
    assert po.status_code == 201, po.data
    grn = client.post(
        "/api/v1/pharmacy/grn",
        {
            "supplier_id": supplier_id,
            "purchase_order_id": po.data["id"],
            "lines": [
                {
                    "drug_id": str(para.id),
                    "purchase_order_line_id": po.data["lines"][0]["id"],
                    "batch_no": "NEAR",
                    "expiry_date": (today + timedelta(days=20)).isoformat(),
                    "quantity": 40,
                    "unit_cost": "1.00",
                },
                {
                    "drug_id": str(para.id),
                    "purchase_order_line_id": po.data["lines"][0]["id"],
                    "batch_no": "FAR",
                    "expiry_date": (today + timedelta(days=200)).isoformat(),
                    "quantity": 60,
                    "unit_cost": "1.00",
                },
            ],
        },
        format="json",
    )
    assert grn.status_code == 201, grn.data

    desk = _login("receptionist")
    patient = desk.post(
        "/api/v1/patients/register",
        {"first_name": "Pharma", "gender": "M", "mobile": "9811177001", "age_years": 40},
        format="json",
    )
    assert patient.status_code == 201, patient.data

    sale = client.post(
        "/api/v1/pharmacy/sales",
        {
            "kind": "COUNTER",
            "patient_id": patient.data["id"],
            "paid_amount": "20.00",
            "items": [{"drug_id": str(para.id), "quantity": 10}],
        },
        format="json",
    )
    assert sale.status_code == 201, sale.data
    assert sale.data["lines"][0]["batch_no"] == "NEAR"
    assert sale.data["bill"]["status"] == "PAID"

    near = StockBatch.objects.get(batch_no="NEAR")
    far = StockBatch.objects.get(batch_no="FAR")
    assert near.quantity_on_hand == 30
    assert far.quantity_on_hand == 60


@pytest.mark.django_db
def test_insufficient_stock_and_near_expiry_flag(seeded_db):
    client = _login()
    para = Drug.objects.get(code="PARA500")
    today = timezone.localdate()
    _receive(client, str(para.id), "SMALL", today + timedelta(days=10), 5)
    sale = client.post(
        "/api/v1/pharmacy/sales",
        {"kind": "COUNTER", "items": [{"drug_id": str(para.id), "quantity": 6}]},
        format="json",
    )
    assert sale.status_code == 400
    assert sale.data["code"] == "insufficient_stock"

    inv = client.get("/api/v1/pharmacy/inventory?near_expiry_days=30")
    assert inv.status_code == 200
    assert any(b["batch_no"] == "SMALL" for b in inv.data["near_expiry"])


@pytest.mark.django_db
def test_return_restores_stock_and_h1_register(seeded_db):
    client = _login()
    tram = Drug.objects.get(code="TRAM50")
    today = timezone.localdate()
    _receive(client, str(tram.id), "H1B", today + timedelta(days=90), 20, unit_cost="5.00")
    desk = _login("receptionist")
    patient = desk.post(
        "/api/v1/patients/register",
        {"first_name": "Ctrl", "gender": "F", "mobile": "9811177002", "age_years": 45},
        format="json",
    )
    sale = client.post(
        "/api/v1/pharmacy/sales",
        {
            "kind": "COUNTER",
            "patient_id": patient.data["id"],
            "paid_amount": "20.00",
            "items": [{"drug_id": str(tram.id), "quantity": 2}],
        },
        format="json",
    )
    assert sale.status_code == 201, sale.data
    assert ControlledDrugEntry.objects.filter(drug=tram, quantity=2).exists()

    returned = client.post(
        "/api/v1/pharmacy/returns",
        {"sale_line_id": sale.data["lines"][0]["id"], "quantity": 1, "reason": "Patient declined"},
        format="json",
    )
    assert returned.status_code == 201, returned.data
    batch = StockBatch.objects.get(batch_no="H1B")
    assert batch.quantity_on_hand == 19


@pytest.mark.django_db
def test_dump_stock_and_doctor_denied(seeded_db):
    client = _login()
    para = Drug.objects.get(code="PARA500")
    today = timezone.localdate()
    _receive(client, str(para.id), "DUMP1", today + timedelta(days=60), 15)
    batch = StockBatch.objects.get(batch_no="DUMP1")
    dumped = client.post(
        "/api/v1/pharmacy/adjust",
        {"batch_id": str(batch.id), "kind": "DUMP", "quantity": 5, "remarks": "Damaged"},
        format="json",
    )
    assert dumped.status_code == 200, dumped.data
    assert dumped.data["quantity_on_hand"] == 10

    doctor = _login("doctor")
    denied = doctor.post(
        "/api/v1/pharmacy/sales",
        {"kind": "COUNTER", "items": [{"drug_id": str(para.id), "quantity": 1}]},
        format="json",
    )
    assert denied.status_code == 403
