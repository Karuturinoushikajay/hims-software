from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from django.db import connection, transaction
from django.test import TransactionTestCase

from apps.numbering.models import DocumentType, NumberSequence
from apps.numbering.services import allocate, financial_year_label
from apps.organizations.models import Facility, Organization


@pytest.mark.django_db
def test_financial_year_label_april_start():
    assert financial_year_label(date(2026, 3, 31)) == "2025-26"
    assert financial_year_label(date(2026, 4, 1)) == "2026-27"


@pytest.mark.django_db
def test_uhid_does_not_reset_with_fy(seeded_db):
    org = Organization.objects.get(code="DHG")
    n1 = allocate(document_type=DocumentType.UHID, organization=org)
    n2 = allocate(document_type=DocumentType.UHID, organization=org)
    assert n1.endswith("000001")
    assert n2.endswith("000002")
    assert "/MR/" in n1
    seq = NumberSequence.objects.get(organization=org, document_type=DocumentType.UHID)
    assert seq.financial_year == ""


@pytest.mark.django_db
def test_fy_rollover_starts_new_series(seeded_db):
    facility = Facility.objects.get(code="DMSH")
    a = allocate(
        document_type=DocumentType.BILL,
        facility=facility,
        on_date=date(2026, 3, 31),
    )
    b = allocate(
        document_type=DocumentType.BILL,
        facility=facility,
        on_date=date(2026, 4, 1),
    )
    assert "2025-26" in a
    assert "2026-27" in b
    assert a.endswith("000001")
    assert b.endswith("000001")


@pytest.mark.django_db
def test_rollback_does_not_consume_number(seeded_db):
    facility = Facility.objects.get(code="DMSH")
    seq = NumberSequence.objects.get(
        facility=facility,
        document_type=DocumentType.BILL,
        financial_year=financial_year_label(date.today()),
    )
    before = seq.next_value
    try:
        with transaction.atomic():
            allocate(document_type=DocumentType.BILL, facility=facility)
            raise RuntimeError("force rollback")
    except RuntimeError:
        pass
    seq.refresh_from_db()
    assert seq.next_value == before


class ConcurrentAllocationTests(TransactionTestCase):
    def setUp(self):
        from django.conf import settings
        from django.core.management import call_command

        settings.DEBUG = True
        if not settings.DEMO_SEED_PASSWORD:
            settings.DEMO_SEED_PASSWORD = "ChangeMeDemo!2026"
        call_command("seed_demo", force=True)

    def test_concurrent_bill_allocation_gap_free(self):
        facility_id = str(Facility.objects.get(code="DMSH").id)

        def worker(_):
            connection.close()
            try:
                facility = Facility.objects.get(id=facility_id)
                with transaction.atomic():
                    return allocate(document_type=DocumentType.BILL, facility=facility)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(worker, range(20)))

        assert len(results) == len(set(results))
        suffixes = sorted(int(r.split("/")[-1]) for r in results)
        assert suffixes == list(range(1, 21))
        connection.close()

