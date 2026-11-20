from __future__ import annotations

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler


class AppError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "error"
    default_detail = "Request failed."

    def __init__(self, message: str | None = None, code: str | None = None, fields=None):
        self.code = code or self.default_code
        self.fields = fields or {}
        detail = message or self.default_detail
        super().__init__(detail=detail, code=self.code)


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "conflict"


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "forbidden"


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_code = "unauthorized"


class ThrottledError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_code = "throttled"


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, AppError):
        payload = {
            "code": exc.code,
            "message": str(exc.detail),
            "fields": exc.fields or {},
        }
        return Response(payload, status=exc.status_code)

    code = getattr(exc, "default_code", "error")
    if isinstance(exc.detail, dict):
        message = "Validation failed."
        fields = exc.detail
    elif isinstance(exc.detail, list):
        message = "; ".join(str(x) for x in exc.detail)
        fields = {}
    else:
        message = str(exc.detail)
        fields = {}

    return Response(
        {"code": code, "message": message, "fields": fields},
        status=response.status_code,
    )
