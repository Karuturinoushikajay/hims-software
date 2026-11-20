from __future__ import annotations

import logging
import threading

_local = threading.local()


def set_request_id(request_id: str) -> None:
    _local.request_id = request_id


def get_request_id() -> str:
    return getattr(_local, "request_id", "-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True
