"""Request ID and access logging.

Exactly one access log line per request, on success and on error alike. The
path is logged without its query string so filter values and any token
accidentally placed in a URL never reach the log.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

logger = logging.getLogger("desk.access")

_request_id_attr = "request_id"


class RequestIDMiddleware:
    """Attach a request id used by both the access log and error bodies."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        setattr(request, _request_id_attr, uuid.uuid4().hex)
        response = self.get_response(request)
        response["X-Request-ID"] = getattr(request, _request_id_attr, "")
        return response


class AccessLogMiddleware:
    """Log method, path, status, duration and user id for every request."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Monotonic: immune to wall-clock adjustment mid-request.
        started = time.monotonic()
        status = 500
        try:
            response = self.get_response(request)
            status = response.status_code
            return response
        finally:
            self._log(request, status, time.monotonic() - started)

    @staticmethod
    def _log(request: HttpRequest, status: int, elapsed: float) -> None:
        user = getattr(request, "user", None)
        user_id = None
        if user is not None and getattr(user, "is_authenticated", False):
            user_id = str(user.pk)
        logger.info(
            "request",
            extra={
                "method": request.method,
                # request.path excludes the query string by construction.
                "path": request.path,
                "status": status,
                "duration_ms": round(elapsed * 1000, 2),
                "user_id": user_id,
                "request_id": getattr(request, _request_id_attr, None),
            },
        )
