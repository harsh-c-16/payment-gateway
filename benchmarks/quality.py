"""Deterministic W-QUALITY logical expectations, not a Kafka producer or event SDK."""

import hashlib
import random

from projectctl.artifacts import canonical_json

SUBCASES = (
    ("invalid_json", "INVALID_JSON"),
    ("invalid_utf8", "INVALID_UTF8"),
    ("missing_event_id", "MISSING_REQUIRED"),
    ("missing_payload", "MISSING_REQUIRED"),
    ("wrong_money_type", "INVALID_TYPE"),
    ("negative_quantity", "INVALID_QUANTITY"),
    ("unsupported_schema", "UNSUPPORTED_SCHEMA"),
    ("unsupported_major", "UNSUPPORTED_SCHEMA"),
    ("wrong_key", "KEY_MISMATCH"),
    ("non_utc_timestamp", "INVALID_TIMESTAMP"),
)


def quality_expectations(seed=42):
    """Each duplicate points to identical logical bytes at an earlier record ordinal.

    Runtime UUIDs, exact wire bytes/schema IDs, SKU mapping and source coordinates
    must be materialized by the reviewed provider SDK in later milestones.
    """
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    originals = {}
    for index in range(98500):
        event_id = f"logical-event-{index:06}"
        content = canonical_json(
            {
                "logical_event_id": event_id,
                "logical_key": index % 10000,
                "event_type": "STOCK_UPDATED",
                "version": index // 10000 + 1,
            }
        )
        digest = hashlib.sha256(content).hexdigest()
        originals[index] = digest
        yield {
            "record_ordinal": index,
            "logical_record_id": f"source-{index:06}",
            "logical_event_id": event_id,
            "expected_disposition": "new_valid",
            "logical_content_sha256": digest,
            "duplicate_of": None,
            "invalid_subcase": None,
            "reason_code": None,
        }
    for number, original in enumerate(random.Random(seed).sample(range(98500), 1000), 98500):
        yield {
            "record_ordinal": number,
            "logical_record_id": f"source-{number:06}",
            "logical_event_id": f"logical-event-{original:06}",
            "expected_disposition": "duplicate_delivery",
            "logical_content_sha256": originals[original],
            "duplicate_of": original,
            "invalid_subcase": None,
            "reason_code": None,
        }
    for offset, (subcase, reason) in enumerate(SUBCASES):
        for index in range(50):
            number = 99500 + 50 * offset + index
            yield {
                "record_ordinal": number,
                "logical_record_id": f"source-{number:06}",
                "logical_event_id": None,
                "expected_disposition": "invalid",
                "logical_content_sha256": None,
                "duplicate_of": None,
                "invalid_subcase": subcase,
                "reason_code": reason,
            }
