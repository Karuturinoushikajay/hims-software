from __future__ import annotations

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        db_ok = False
        cache_ok = False
        redis_ok = False
        try:
            connection.ensure_connection()
            db_ok = True
        except Exception:  # noqa: BLE001
            db_ok = False
        try:
            cache.set("healthcheck", "1", 5)
            cache_ok = cache.get("healthcheck") == "1"
        except Exception:  # noqa: BLE001
            cache_ok = False

        if getattr(settings, "USE_REDIS_CACHE", False):
            redis_ok = cache_ok
            status_code = 200 if db_ok and redis_ok else 503
        else:
            redis_ok = False  # not configured
            status_code = 200 if db_ok and cache_ok else 503

        return Response(
            {
                "status": "ok" if status_code == 200 else "degraded",
                "database": db_ok,
                "cache": cache_ok,
                "redis": redis_ok,
                "redis_required": bool(getattr(settings, "USE_REDIS_CACHE", False)),
            },
            status=status_code,
        )
