from __future__ import annotations

import pytest
from django.db import connection, transaction

from apps.audit.services import record_audit
from apps.organizations.models import Facility


@pytest.mark.django_db
def test_audit_model_blocks_update(seeded_db):
    facility = Facility.objects.get(code="DMSH")
    row = record_audit(
        action="test.action",
        facility=facility,
        entity_type="Test",
        entity_id="1",
        after={"ok": True},
    )
    with pytest.raises(RuntimeError):
        row.action = "mutated"
        row.save()


@pytest.mark.django_db
def test_audit_model_blocks_delete(seeded_db):
    facility = Facility.objects.get(code="DMSH")
    row = record_audit(action="test.delete", facility=facility)
    with pytest.raises(RuntimeError):
        row.delete()


@pytest.mark.django_db(transaction=True)
def test_audit_db_trigger_blocks_update_delete(seeded_db):
    facility = Facility.objects.get(code="DMSH")
    row = record_audit(action="test.trigger", facility=facility)
    with connection.cursor() as cursor:
        with pytest.raises(Exception):
            cursor.execute(
                "UPDATE audit_auditlog SET action = %s WHERE id = %s",
                ["hacked", str(row.id)],
            )
    # Fresh connection state after failed statement inside transaction=True test.
    connection.rollback()
    with connection.cursor() as cursor:
        with pytest.raises(Exception):
            with transaction.atomic():
                cursor.execute("DELETE FROM audit_auditlog WHERE id = %s", [str(row.id)])
