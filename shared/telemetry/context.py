"""Task-local context and structured logs without request bodies or exception text."""

import json
import math
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime

from shared.contracts.common import RequestContext

_context = ContextVar("telemetry_context", default=None)


def utc_now():
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@contextmanager
def bind_context(context: RequestContext, service: str):
    if not service or not isinstance(context, RequestContext):
        raise ValueError("service and canonical RequestContext required")
    token = _context.set((context.model_copy(deep=True), service))
    try:
        yield
    finally:
        _context.reset(token)


def log_operation(logger, operation, outcome, duration_seconds, *, resource_id=None):
    current = _context.get()
    if current is None:
        raise ValueError("bind request context before logging")
    if (
        isinstance(duration_seconds, bool)
        or not math.isfinite(duration_seconds)
        or duration_seconds < 0
    ):
        raise ValueError("finite monotonic elapsed duration required")
    context, service = current
    record = {
        "timestamp": utc_now(),
        "service": service,
        "operation": operation,
        "outcome": outcome,
        "duration_seconds": duration_seconds,
        "resource_id": resource_id,
        **context.model_dump(),
    }
    logger.info(json.dumps(record, sort_keys=True, allow_nan=False))
    return record
