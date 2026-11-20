from __future__ import annotations

from apps.audit.models import AuditLog
from apps.common.logging import get_request_id


def _ip_from_request(request) -> str | None:
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def record_audit(
    *,
    action: str,
    actor=None,
    facility=None,
    entity_type: str = "",
    entity_id: str | None = "",
    before=None,
    after=None,
    request=None,
) -> AuditLog:
    ip = _ip_from_request(request)
    ua = ""
    request_id = get_request_id()
    if request is not None:
        ua = request.META.get("HTTP_USER_AGENT", "")[:1000]
        request_id = getattr(request, "request_id", None) or request_id

    return AuditLog.objects.create(
        action=action,
        actor=actor if actor and getattr(actor, "is_authenticated", False) else None,
        facility=facility,
        entity_type=entity_type or "",
        entity_id=str(entity_id) if entity_id else "",
        before=before,
        after=after,
        ip_address=ip,
        user_agent=ua,
        request_id=request_id if request_id != "-" else "",
    )
