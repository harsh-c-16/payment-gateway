"""Neutral wire primitives. Header bindings require provider/consumer G0 review."""

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
)

INT64_MAX = 2**63 - 1
Money = Annotated[int, Field(strict=True, ge=0, le=INT64_MAX)]
Version = Annotated[int, Field(strict=True, ge=0, le=INT64_MAX)]
Sku = Annotated[str, StringConstraints(pattern=r"^[!-~]{1,64}$")]
Identifier = Annotated[str, StringConstraints(min_length=1, max_length=128, pattern=r"^[!-~]+$")]
IdempotencyKey = Annotated[
    str, StringConstraints(min_length=1, max_length=128, pattern=r"^[ -~]+$")
]


def uuid_text(value: str) -> str:
    if str(UUID(value)) != value:
        raise ValueError("expected a canonical lowercase UUID")
    return value


UUIDText = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$"),
    Field(json_schema_extra={"format": "uuid"}),
    AfterValidator(uuid_text),
]


def utc_time(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset().total_seconds() != 0:
        raise ValueError("expected a timezone-aware UTC timestamp")
    return value


def utc_input(value):
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|\+00:00)", value
    ):
        raise ValueError("expected RFC 3339 UTC text")
    return value


UTCTime = Annotated[
    datetime,
    Field(json_schema_extra={"pattern": r"(Z|\+00:00)$"}),
    BeforeValidator(utc_input),
    AfterValidator(utc_time),
]


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class RequestContext(WireModel):
    namespace: Annotated[
        str, StringConstraints(pattern=r"^(dev|bench-[a-z0-9-]+|replay-[a-z0-9-]+)$", max_length=62)
    ]
    run_id: Identifier
    user_id: Identifier
    correlation_id: Identifier
    request_id: UUIDText
    session_id: UUIDText | None
    trace_id: Identifier | None = None

    def headers(self, idempotency_key: str | None = None) -> dict[str, str]:
        # Only correlation/run/user header names are frozen in common §2.
        # The remaining explicit bindings are proposed in docs/jaineel/p2_contracts.md.
        result = {
            "X-Namespace": self.namespace,
            "X-Run-ID": self.run_id,
            "X-User-ID": self.user_id,
            "X-Correlation-ID": self.correlation_id,
            "X-Request-ID": self.request_id,
        }
        if self.session_id is not None:
            result["X-Session-ID"] = self.session_id
        if self.trace_id is not None:
            result["X-Trace-ID"] = self.trace_id
        if idempotency_key is not None:
            from pydantic import TypeAdapter

            result["Idempotency-Key"] = TypeAdapter(IdempotencyKey).validate_python(idempotency_key)
        return result


class ErrorCode(StrEnum):
    BAD_REQUEST = "BAD_REQUEST"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    CART_VERSION_CONFLICT = "CART_VERSION_CONFLICT"
    QUOTE_EXPIRED = "QUOTE_EXPIRED"
    PRODUCT_NOT_SELLABLE = "PRODUCT_NOT_SELLABLE"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    RESERVATION_EXPIRED = "RESERVATION_EXPIRED"
    ALREADY_COMMITTED = "ALREADY_COMMITTED"
    ILLEGAL_STATE = "ILLEGAL_STATE"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNSUPPORTED_CURRENCY = "UNSUPPORTED_CURRENCY"
    UNSUPPORTED_FILTER = "UNSUPPORTED_FILTER"
    RATE_LIMITED = "RATE_LIMITED"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"


class ErrorBody(WireModel):
    code: ErrorCode
    message: str
    retryable: Annotated[bool, Field(strict=True)]
    details: dict[str, str | list[str]]


class ErrorResponse(WireModel):
    error: ErrorBody
    correlation_id: Identifier
