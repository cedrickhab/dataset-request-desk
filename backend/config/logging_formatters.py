"""Structured log formatting.

One JSON object per line. Extra fields are carried on the record by the access
log middleware; nothing here reads request bodies, cookies or headers.
"""

from __future__ import annotations

import json
import logging

# Attributes LogRecord always defines. Anything outside this set was attached
# deliberately via logger.info(..., extra={...}) and is safe to emit.
_RESERVED = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "stacklevel",
        "taskName",
        "thread",
        "threadName",
    }
)


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            # Type name only. Tracebacks stay out of the structured stream so
            # they cannot leak into a client-visible log shipper.
            payload["exception"] = record.exc_info[0].__name__ if record.exc_info[0] else None
        return json.dumps(payload, default=str)
