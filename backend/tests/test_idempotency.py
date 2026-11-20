from __future__ import annotations

import pytest

from apps.common.exceptions import ConflictError
from apps.common.idempotency import begin_or_replay, store_response
from apps.organizations.models import Facility


@pytest.mark.django_db
def test_idempotency_replay_returns_stored_result(seeded_db):
    facility = Facility.objects.get(code="DMSH")
    record, cached, status = begin_or_replay(
        facility=facility,
        key="pay-1",
        method="POST",
        path="/api/v1/payments",
        body={"amount": "100.00"},
    )
    assert cached is None
    store_response(record, 201, {"receipt": "R1"})

    record2, cached2, status2 = begin_or_replay(
        facility=facility,
        key="pay-1",
        method="POST",
        path="/api/v1/payments",
        body={"amount": "100.00"},
    )
    assert cached2 == {"receipt": "R1"}
    assert status2 == 201
    assert record2.id == record.id


@pytest.mark.django_db
def test_idempotency_mismatch_body(seeded_db):
    facility = Facility.objects.get(code="DMSH")
    record, _, _ = begin_or_replay(
        facility=facility,
        key="pay-2",
        method="POST",
        path="/api/v1/payments",
        body={"amount": "100.00"},
    )
    store_response(record, 201, {"ok": True})
    with pytest.raises(ConflictError):
        begin_or_replay(
            facility=facility,
            key="pay-2",
            method="POST",
            path="/api/v1/payments",
            body={"amount": "200.00"},
        )
