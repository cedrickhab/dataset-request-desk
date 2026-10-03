"""Uniform error envelope: {"error": {code, message, fields?}, "request_id"}."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class WorkflowConflict(exceptions.APIException):
    """409: the stored state does not permit this operation."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "The request state changed; reload and try again."
    default_code = "conflict"


class UploadTooLarge(exceptions.APIException):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_detail = "The uploaded file is too large."
    default_code = "upload_too_large"


class ServiceUnavailable(exceptions.APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "A dependency is unavailable."
    default_code = "unavailable"


_CODE_BY_STATUS = {
    400: "validation_error",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "upload_too_large",
    415: "unsupported_media_type",
    429: "throttled",
    503: "unavailable",
}

_MESSAGE_BY_STATUS = {
    401: "Authentication is required.",
    403: "You do not have permission to perform this action.",
    404: "Not found.",
}

# DRF's own generic default_codes. When an exception carries one of these it
# tells us nothing the status code does not, so the contract's status-derived
# code wins. A code outside this set came from one of our own exceptions
# (last_admin_protected, self_deactivation, upload_too_large, ...) and is more
# specific than the status, so it is kept.
_GENERIC_DRF_CODES = frozenset(
    {
        "invalid",
        "parse_error",
        "authentication_failed",
        "not_authenticated",
        "permission_denied",
        "not_found",
        "method_not_allowed",
        "not_acceptable",
        "unsupported_media_type",
        "throttled",
        "error",
    }
)


def _flatten(detail: Any) -> tuple[str, dict[str, Any] | None]:
    """Split a DRF detail into a human message and an optional field map."""
    if isinstance(detail, dict):
        non_field = detail.get("detail")
        if isinstance(non_field, str) and len(detail) == 1:
            return non_field, None
        fields = {key: _as_messages(value) for key, value in detail.items()}
        message = "The submitted data is invalid."
        return message, fields
    if isinstance(detail, list):
        messages = _as_messages(detail)
        return (messages[0] if messages else "Invalid input."), None
    return str(detail), None


def _as_messages(value: Any) -> Any:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, dict):
        return {key: _as_messages(item) for key, item in value.items()}
    return [str(value)]


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    # Translate Django-level exceptions so they get the same envelope.
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()

    response = drf_exception_handler(exc, context)
    if response is None:
        # Unhandled server error: let Django's 500 handling take over rather
        # than inventing a body that might carry internal detail.
        return None

    request = context.get("request")
    request_id = getattr(request, "request_id", None) if request else None
    status_code = _CODE_BY_STATUS.get(response.status_code, "error")
    specific = getattr(exc, "default_code", None)
    code = status_code if specific in _GENERIC_DRF_CODES or not specific else specific
    message, fields = _flatten(response.data)
    if response.status_code in _MESSAGE_BY_STATUS and not fields:
        # DRF's stock wording for these is fine, but keep it uniform.
        message = _MESSAGE_BY_STATUS[response.status_code]

    error: dict[str, Any] = {"code": code, "message": message}
    if fields:
        error["fields"] = fields

    headers = {}
    if response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            headers["Retry-After"] = retry_after

    return Response(
        {"error": error, "request_id": request_id},
        status=response.status_code,
        headers=headers or None,
    )
