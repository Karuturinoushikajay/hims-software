from __future__ import annotations

from datetime import UTC, datetime

from django.conf import settings
from django.utils import timezone

from apps.organizations.models import Facility


class IdleSessionMiddleware:
    """Enforce idle timeout from facility settings (fallback: SESSION_COOKIE_AGE)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            last = request.session.get("_last_activity")
            timeout = request.session.get(
                "_idle_timeout_seconds",
                settings.SESSION_COOKIE_AGE,
            )
            now = timezone.now()
            if last:
                last_dt = datetime.fromisoformat(last)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=UTC)
                elapsed = (now - last_dt).total_seconds()
                if elapsed > timeout:
                    from django.contrib.auth import logout

                    logout(request)
                    request.session.flush()
                    response = self.get_response(request)
                    return response
            request.session["_last_activity"] = now.isoformat()
        return self.get_response(request)



class ActiveFacilityMiddleware:
    """Resolve active facility from session onto request.facility."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.facility = None
        facility_id = request.session.get("active_facility_id")
        if facility_id and getattr(request, "user", None) and request.user.is_authenticated:
            try:
                facility = Facility.objects.select_related("organization", "settings").get(
                    id=facility_id,
                    is_active=True,
                    deleted_at__isnull=True,
                )
                # Superusers may access any facility; others need membership.
                if request.user.is_superuser or request.user.memberships.filter(
                    facility=facility,
                    is_active=True,
                    deleted_at__isnull=True,
                ).exists():
                    request.facility = facility
                    settings_obj = getattr(facility, "settings", None)
                    if settings_obj:
                        request.session["_idle_timeout_seconds"] = (
                            settings_obj.session_timeout_minutes * 60
                        )
            except Facility.DoesNotExist:
                request.session.pop("active_facility_id", None)
        return self.get_response(request)
