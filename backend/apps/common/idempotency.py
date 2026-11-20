from __future__ import annotations

import hashlib
import json

from django.db import transaction

from apps.common.models import IdempotencyKey


def _hash_body(body: dict | None) -> str:
    raw = json.dumps(body or {}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@transaction.atomic
def begin_or_replay(
    *,
    facility,
    key: str,
    method: str,
    path: str,
    body: dict | None,
    user=None,
) -> tuple[IdempotencyKey, dict | None, int | None]:
    """
    Return (record, cached_response_body, cached_status).
    If cached_response_body is not None, the caller must replay it.
    """
    request_hash = _hash_body(body)
    existing = (
        IdempotencyKey.objects.select_for_update()
        .filter(facility=facility, key=key)
        .first()
    )
    if existing:
        if existing.request_hash and existing.request_hash != request_hash:
            from apps.common.exceptions import ConflictError

            raise ConflictError(
                "Idempotency key reused with a different request body.",
                code="idempotency_mismatch",
            )
        if existing.response_body is not None and existing.response_status is not None:
            return existing, existing.response_body, existing.response_status
        return existing, None, None

    record = IdempotencyKey.objects.create(
        facility=facility,
        key=key,
        method=method,
        path=path,
        request_hash=request_hash,
        user=user,
    )
    return record, None, None


def store_response(record: IdempotencyKey, status_code: int, body: dict) -> None:
    record.response_status = status_code
    record.response_body = body
    record.save(update_fields=["response_status", "response_body", "updated_at"])
