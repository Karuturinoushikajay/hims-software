from __future__ import annotations

from django.utils.dateparse import parse_datetime
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import require_permission
from apps.audit.models import AuditLog
from apps.common.exceptions import AppError


class AuditLogListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = getattr(request, "facility", None)
        if not facility:
            raise AppError("No active facility.", code="no_facility")
        require_permission(request.user, facility, "audit.read")

        qs = AuditLog.objects.filter(facility=facility).select_related("actor")
        actor = request.query_params.get("actor")
        action = request.query_params.get("action")
        date_from = request.query_params.get("from")
        date_to = request.query_params.get("to")

        if actor:
            qs = qs.filter(actor__username__icontains=actor)
        if action:
            qs = qs.filter(action__icontains=action)
        if date_from:
            dt = parse_datetime(date_from)
            if dt:
                qs = qs.filter(created_at__gte=dt)
        if date_to:
            dt = parse_datetime(date_to)
            if dt:
                qs = qs.filter(created_at__lte=dt)

        qs = qs[:200]
        return Response(
            [
                {
                    "id": str(row.id),
                    "created_at": row.created_at.isoformat(),
                    "action": row.action,
                    "actor": row.actor.username if row.actor_id else None,
                    "entity_type": row.entity_type,
                    "entity_id": row.entity_id,
                    "before": row.before,
                    "after": row.after,
                    "ip_address": row.ip_address,
                    "request_id": row.request_id,
                }
                for row in qs
            ]
        )
