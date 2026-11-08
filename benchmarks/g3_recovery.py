"""Consumer regression for quote expiry versus already-accepted identity.

The owner supplies expired accepted/unconsumed quotes in an isolated namespace.
No clock rewrite, direct database write, replacement quote or Orders patch.
"""

from datetime import UTC, datetime

from benchmarks.g3_http import HTTPFailure
from projectctl.providers import DependencyError
from shared.contracts.catalog import Quote
from shared.contracts.transactions import CreateOrderRequest, OrderAccepted


async def probe_quote_expiry(
    http,
    context,
    principal,
    *,
    accepted_request,
    order_id,
    original_key,
    retry_key,
    fresh_expired_request,
):
    accepted_request = CreateOrderRequest.model_validate(accepted_request).model_dump(mode="json")
    fresh_expired_request = CreateOrderRequest.model_validate(fresh_expired_request).model_dump(
        mode="json"
    )
    if (
        original_key == retry_key
        or accepted_request["quote_id"] == fresh_expired_request["quote_id"]
    ):
        raise ValueError("distinct transport key and unconsumed expired quote required")
    for request in (accepted_request, fresh_expired_request):
        quoted = await http.call(
            context,
            principal,
            "catalog",
            "GET",
            "/internal/v1/quotes/" + request["quote_id"],
            model=Quote,
        )
        if (
            quoted["quote_id"] != request["quote_id"]
            or quoted["user_id"] != principal.user_id
            or datetime.fromisoformat(quoted["expires_at"].replace("Z", "+00:00"))
            >= datetime.now(UTC)
        ):
            raise DependencyError(
                "consumer expiry probe requires backend expired quotes for this user"
            )
    receipts = []
    for key in (original_key, retry_key):
        result = await http.call(
            context,
            principal,
            "orders",
            "POST",
            "/v1/orders",
            202,
            body=accepted_request,
            key=key,
            model=OrderAccepted,
        )
        if result["order_id"] != order_id:
            raise DependencyError("accepted quote retry created a different order")
        receipts.append(result)
    try:
        await http.call(
            context,
            principal,
            "orders",
            "POST",
            "/v1/orders",
            202,
            body=fresh_expired_request,
            key=retry_key + ":fresh",
            model=OrderAccepted,
        )
    except HTTPFailure as error:
        if (error.status, error.code) != (409, "QUOTE_EXPIRED"):
            raise DependencyError("new expired quote must return 409 QUOTE_EXPIRED") from None
    else:
        raise DependencyError("Orders accepted a new expired quote; owner repair required")
    try:
        await http.call(
            context,
            principal,
            "orders",
            "POST",
            "/v1/orders",
            202,
            body=fresh_expired_request,
            key=original_key,
            model=OrderAccepted,
        )
    except HTTPFailure as error:
        if (error.status, error.code) != (409, "IDEMPOTENCY_CONFLICT"):
            raise DependencyError(
                "changed input with original key must conflict before expiry"
            ) from None
    else:
        raise DependencyError("Orders reused an idempotency key for changed business input")
    return {
        "same_order_retries": receipts,
        "new_expired_rejected": True,
        "changed_input_conflicted": True,
    }
