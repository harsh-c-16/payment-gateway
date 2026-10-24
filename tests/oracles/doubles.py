"""Explicit evidence snapshots for oracle unit tests, not a running provider."""

import copy


def clean_evidence():
    lines = [
        {
            "sku": "FIXTURE-SKU",
            "quantity": 1,
            "unit_price_minor": 100,
            "line_total_minor": 100,
            "catalog_version": 1,
        }
    ]
    quote = {
        "quote_id": "fixture-quote",
        "currency": "INR",
        "total_amount_minor": 100,
        "lines": lines,
        "user_id": "fixture-user",
        "session_id": "fixture-session",
    }
    expected = {
        "namespace": "bench-oracle-fixture",
        "events": {"event-a": "a" * 64, "event-b": "b" * 64},
        "source_dispositions": {
            "source-a": "new_valid",
            "source-b": "new_valid",
            "source-duplicate": "duplicate_delivery",
            "source-invalid": "invalid",
        },
        "gold_totals_by_currency": {"INR": 100},
        "gold_business_rows": {"pipeline_minute:fixture": {"event_count": 2}},
        "orders": {"fixture-order": quote},
        "opening_stock": {"FIXTURE-SKU": 10},
        "replenishment": {"FIXTURE-SKU": 0},
        "source_manifest_ids": ["fixture-source-manifest"],
    }
    observed = {
        "namespace": expected["namespace"],
        "test_mode": "stub",
        "collection_complete": True,
        "source_dispositions": [
            {"record_id": key, "disposition": value}
            for key, value in expected["source_dispositions"].items()
        ],
        "silver_events": [
            {"event_id": key, "content_sha256": value} for key, value in expected["events"].items()
        ],
        "active_gold": {
            "namespace": expected["namespace"],
            "generation": 4,
            "query_generation": 4,
            "manifest_sha256": "c" * 64,
            "query_manifest_sha256": "c" * 64,
            "source_manifest_ids": expected["source_manifest_ids"],
            "membership_ids": list(expected["events"]),
            "visibility_receipts": [
                {"event_id": key, "generation": 4, "manifest_sha256": "c" * 64}
                for key in expected["events"]
            ],
            "totals_by_currency": {"INR": 100},
            "business_rows": expected["gold_business_rows"],
        },
        "orders": [{"order_id": "fixture-order", "status": "CONFIRMED", **quote}],
        "reservations": [
            {
                "order_id": "fixture-order",
                "state": "COMMITTED",
                "items": [{"sku": "FIXTURE-SKU", "quantity": 1}],
            }
        ],
        "payments": [
            {
                "order_id": "fixture-order",
                "payment_id": "fixture-payment",
                "attempt_number": 1,
                "status": "SUCCESS",
                "amount_minor": 100,
                "currency": "INR",
            }
        ],
        "payment_guards": {"fixture-order": {"quiesced": False}},
        "ledger": [
            {
                "entry_id": "fixture-debit",
                "order_id": "fixture-order",
                "payment_id": "fixture-payment",
                "kind": "DEBIT",
                "amount_minor": 100,
                "currency": "INR",
            }
        ],
        "stocks": [
            {"sku": "FIXTURE-SKU", "on_hand": 9, "reserved": 0, "available": 9, "replenished": 0}
        ],
    }
    # Ensure independent expected values cannot be mutated by editing observed snapshots.
    return copy.deepcopy(expected), copy.deepcopy(observed)


def corrupt_evidence(name, observed):
    observed = copy.deepcopy(observed)
    if name == "missing-event":
        observed["silver_events"].pop()
    elif name == "duplicate-silver":
        observed["silver_events"].append(copy.deepcopy(observed["silver_events"][0]))
    elif name == "duplicate-source-disposition":
        observed["source_dispositions"].append(copy.deepcopy(observed["source_dispositions"][0]))
    elif name == "bad-source-disposition":
        observed["source_dispositions"][0]["disposition"] = "invalid"
    elif name == "bad-content":
        observed["silver_events"][0]["content_sha256"] = "d" * 64
    elif name == "bad-gold-total":
        observed["active_gold"]["totals_by_currency"]["INR"] = 101
    elif name == "bad-gold-row":
        observed["active_gold"]["business_rows"]["pipeline_minute:fixture"]["event_count"] = 3
    elif name == "duplicate-gold":
        observed["active_gold"]["membership_ids"].append("event-a")
    elif name == "false-gold-visibility":
        observed["active_gold"]["membership_ids"].remove("event-a")
    elif name == "stale-generation":
        observed["active_gold"]["query_generation"] = 3
    elif name == "stale-manifest-hash":
        observed["active_gold"]["query_manifest_sha256"] = "d" * 64
    elif name == "stale-source-manifest":
        observed["active_gold"]["source_manifest_ids"] = ["older-source-manifest"]
    elif name == "bad-order-total":
        observed["orders"][0]["total_amount_minor"] = 101
    elif name == "duplicate-debit-reversed":
        observed["ledger"].append({**observed["ledger"][0], "entry_id": "duplicate-debit"})
        observed["ledger"].append(
            {
                **observed["ledger"][0],
                "entry_id": "duplicate-reversal",
                "kind": "REVERSAL",
                "amount_minor": -100,
            }
        )
    elif name == "illegal-stock":
        observed["stocks"][0].update(reserved=11, available=-2)
    elif name == "inventory-loss":
        observed["stocks"][0].update(on_hand=8, available=8)
    elif name == "illegal-payment":
        observed["payments"][0]["status"] = "FAILED"
    elif name == "false-cancellation":
        observed["orders"][0]["status"] = "CANCELLED"
    elif name == "payment-currency":
        observed["payments"][0]["currency"] = "USD"
    elif name == "wrong-reservation-items":
        observed["reservations"][0]["items"][0]["quantity"] = 2
    elif name == "duplicate-reservation-line":
        observed["reservations"][0]["items"].append(
            copy.deepcopy(observed["reservations"][0]["items"][0])
        )
        observed["stocks"][0].update(on_hand=8, available=8)
    elif name == "overlapping-payment-attempt":
        observed["payments"].append(
            {
                **observed["payments"][0],
                "payment_id": "second-payment",
                "attempt_number": 2,
                "status": "PENDING",
            }
        )
    elif name == "invented-replenishment":
        observed["stocks"][0].update(on_hand=10, available=10, replenished=1)
    else:
        raise ValueError("unknown explicit corruption")
    return observed


CORRUPTIONS = {
    "missing-event": "MISSING_EXPECTED_IDS",
    "duplicate-silver": "DUPLICATE_SILVER_EFFECT",
    "duplicate-source-disposition": "DUPLICATE_SOURCE_DISPOSITION",
    "bad-source-disposition": "WRONG_SOURCE_DISPOSITION",
    "bad-content": "EVENT_CONTENT_CONFLICT",
    "bad-gold-total": "BAD_GOLD_MONETARY_TOTAL",
    "bad-gold-row": "BAD_GOLD_BUSINESS_ROWS",
    "duplicate-gold": "DUPLICATE_GOLD_EFFECT",
    "false-gold-visibility": "FALSE_GOLD_VISIBILITY",
    "stale-generation": "STALE_MANIFEST_OR_QUERY_GENERATION",
    "stale-manifest-hash": "STALE_MANIFEST_OR_QUERY_GENERATION",
    "stale-source-manifest": "STALE_SOURCE_MANIFEST_REFERENCE",
    "bad-order-total": "IMMUTABLE_QUOTE_ORDER_MISMATCH",
    "duplicate-debit-reversed": "DUPLICATE_DEBIT_EFFECT",
    "illegal-stock": "ILLEGAL_STOCK_STATE",
    "inventory-loss": "INVENTORY_CONSERVATION",
    "illegal-payment": "PAYMENT_STATE_LEDGER_CONFLICT",
    "false-cancellation": "UNRECONCILED_CANCELLATION",
    "payment-currency": "PAYMENT_CURRENCY_MISMATCH",
    "wrong-reservation-items": "RESERVATION_ORDER_ITEMS_MISMATCH",
    "duplicate-reservation-line": "DUPLICATE_RESERVATION_LINE",
    "overlapping-payment-attempt": "OVERLAPPING_PAYMENT_ATTEMPTS",
    "invented-replenishment": "UNEXPECTED_REPLENISHMENT",
}
