from __future__ import annotations

import uuid

from apps.common.logging import set_request_id


class RequestIdMiddleware:
    """Attach a request id to every request for structured logs and audit."""

    HEADER = "HTTP_X_REQUEST_ID"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.META.get(self.HEADER) or str(uuid.uuid4())
        request.request_id = request_id
        set_request_id(request_id)
        response = self.get_response(request)
        response["X-Request-ID"] = request_id
        return response
