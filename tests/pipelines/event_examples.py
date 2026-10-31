"""Small deterministic synthetic examples for producer review, not measured data."""

from uuid import UUID

from shared.contracts.events import EVENTS

NOW = "2026-10-31T10:00:00Z"


def uid(number):
    return str(UUID(int=number))


INTENT = {
    "query_text": "synthetic product",
    "category": None,
    "size": None,
    "colour": None,
    "material": None,
    "brand": None,
    "occasion": None,
    "max_price_minor": None,
    "category_path_prefix": None,
    "currency": "INR",
}


def examples():
    payloads = {
        "CONVERSATION_TURN": {
            "turn_id": uid(1),
            "mode": "fixed",
            "outcome": "success",
            "duration_ms": 12.5,
            "llm_call_count": 0,
            "extractor_source": "rules",
        },
        "INTENT_EXTRACTED": {
            "turn_id": uid(1),
            "intent": INTENT,
            "extractor_version": "rules-v1",
            "outcome": "valid",
        },
        "INTENT_REJECTED": {
            "turn_id": uid(1),
            "reason_code": "MODEL_OUTPUT_INVALID",
            "extractor_version": "rules-v1",
            "restricted_content_reference": "restricted/synthetic-1",
        },
        "TOOL_CALLED": {
            "turn_id": uid(1),
            "tool_call_id": uid(2),
            "tool_name": "search",
            "outcome": "success",
            "duration_ms": 3.0,
        },
        "ADD_TO_CART": {
            "cart_id": uid(3),
            "cart_version": 1,
            "sku": "FK-SYNTHETIC-1",
            "quantity_after": 2,
        },
        "CHECKOUT_STARTED": {
            "cart_id": uid(3),
            "quote_id": uid(4),
            "order_id": uid(5),
            "confirmation_id": uid(6),
        },
        "SEARCH_REQUESTED": {"search_id": uid(7), "intent": INTENT, "mode": "lexical"},
        "PRODUCT_RETRIEVED": {
            "search_id": uid(7),
            "skus": [],
            "returned_count": 0,
            "mode": "lexical",
            "duration_ms": 7.25,
        },
        "PRODUCT_COMPARED": {
            "comparison_id": uid(8),
            "skus": ["FK-SYNTHETIC-1"],
            "field_names": ["price_minor"],
        },
        "PRICE_UPDATED": {
            "sku": "FK-SYNTHETIC-1",
            "price_minor": 219900,
            "currency": "INR",
            "catalog_version": 1,
        },
    }
    for name in EVENTS:
        if name.startswith("ORDER_"):
            payloads[name] = {
                "order_id": uid(5),
                "order_status": {
                    "ORDER_CREATED": "PENDING",
                    "ORDER_CONFIRMED": "CONFIRMED",
                    "ORDER_CANCELLED": "CANCELLED",
                }[name],
                "total_amount_minor": 439800,
                "currency": "INR",
                "created_at": NOW,
                "user_id": "synthetic-user",
                "session_id": uid(10),
                "quote_id": uid(4),
                "failure_code": None,
            }
            if name == "ORDER_CONFIRMED":
                payloads[name].update(reservation_id=uid(11), payment_id=uid(12))
        if name.startswith("INVENTORY_") or name == "STOCK_UPDATED":
            payloads[name] = {
                "sku": "FK-SYNTHETIC-1",
                "on_hand": 3,
                "reserved": 2,
                "available": 1,
                "stock_version": 1,
                "changed_at": NOW,
                "order_id": uid(5),
                "reservation_id": uid(11),
                "reason_code": None,
            }
            if name == "INVENTORY_REJECTED":
                payloads[name].update(reservation_request_id=uid(13), reason_code="OUT_OF_STOCK")
        if name.startswith("PAYMENT_"):
            payloads[name] = {
                "payment_id": uid(12),
                "order_id": uid(5),
                "attempt_number": 1,
                "status": name.removeprefix("PAYMENT_"),
                "amount_minor": 439800,
                "currency": "INR",
                "attempt_created_at": NOW,
                "failure_code": "SIMULATED_FAILURE" if name == "PAYMENT_FAILED" else None,
                "debit_id": uid(14) if name in ("PAYMENT_SUCCESS", "PAYMENT_REVERSED") else None,
                "reversal_id": uid(15) if name == "PAYMENT_REVERSED" else None,
            }
    result = {}
    for number, (name, (_domain, owner, aggregate, _key, _)) in enumerate(EVENTS.items(), 100):
        payload = payloads[name]
        aggregate_id = (
            uid(10)
            if aggregate == "session"
            else payload[
                {
                    "search": "comparison_id" if name == "PRODUCT_COMPARED" else "search_id",
                    "sku": "sku",
                    "order": "order_id",
                    "payment_attempt": "payment_id",
                }[aggregate]
            ]
        )
        result[name] = {
            "event_id": uid(number),
            "event_type": name,
            "schema_version": 1,
            "event_time": NOW,
            "produced_at": NOW,
            "namespace": "bench-m02-examples",
            "run_id": "m02-synthetic",
            "source_service": owner,
            "correlation_id": uid(9),
            "session_id": uid(10),
            "user_id": "synthetic-user",
            "aggregate_type": aggregate,
            "aggregate_id": aggregate_id,
            "aggregate_version": 1,
            "payload": payload,
            "metadata": {
                "dataset_revision": "synthetic-v1",
                "synthetic": True,
                "scenario_source": "simulation",
            },
        }
    result["DLQ_NOTICE"] = {
        "event_id": uid(200),
        "diagnostic_id": uid(200),
        "namespace": "bench-m02-examples",
        "run_id": "m02-synthetic",
        "schema_version": 1,
        "produced_at": NOW,
        "source_service": "conversation",
        "origin_kind": "service_diagnostic",
        "source_locator": "restricted/synthetic-1",
        "reason_code": "MODEL_OUTPUT_INVALID",
        "created_at": NOW,
    }
    return result
