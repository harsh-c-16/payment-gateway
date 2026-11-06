"""Pure W-QUALITY wire binding for the existing harness; never publishes or judges outcomes."""

import json
from datetime import datetime

from benchmarks.scheduler import Packet
from shared.event_transport.schemas import canonical_json


class QualityMaterializer:
    """Use the harness's frozen 10,000-SKU selection from a verified actual catalogue.

    The scheduler persists Packet bytes and reuses the original Packet for duplicates
    and retries. Deliberate invalid bytes need its explicit raw-fixture publisher;
    normal business publishing must continue to validate through the SDK.
    """

    def __init__(self, codec, *, selected_skus, dataset_revision):
        self.skus = tuple(selected_skus)
        if (
            len(self.skus) != 10000
            or any(not isinstance(sku, str) for sku in self.skus)
            or list(self.skus) != sorted(set(self.skus))
            or not isinstance(dataset_revision, str)
            or not dataset_revision.strip()
        ):
            raise ValueError("Frozen sorted unique 10,000-SKU selection and revision required")
        self.codec, self.dataset_revision = codec, dataset_revision

    def __call__(self, record, context):
        if record.get("duplicate_of") is not None:
            raise ValueError(
                "The scheduler must reuse the original persisted Packet for duplicates"
            )
        ordinal = record["record_ordinal"]
        if type(ordinal) is not int or not 0 <= ordinal < 100000:
            raise ValueError("W-QUALITY ordinal outside the frozen fixture")
        if not context["namespace"].startswith("bench-"):
            raise ValueError("Raw quality fixtures require an isolated benchmark namespace")
        subcase = record["invalid_subcase"]
        sku = self.skus[ordinal % 10000]
        version = ordinal // 10000 + 1
        name, aggregate, aggregate_id = "STOCK_UPDATED", "sku", sku
        payload = {
            "sku": sku,
            "stock_version": version,
            "on_hand": 10000,
            "reserved": 0,
            "available": 10000,
            "order_id": None,
            "reservation_id": None,
            "reason_code": None,
            "changed_at": context["scheduled_at"],
        }
        if subcase == "wrong_money_type":
            name = "PRICE_UPDATED"
            payload = {
                "sku": sku,
                "price_minor": 100,
                "currency": "INR",
                "catalog_version": version,
            }
        elif subcase == "negative_quantity":
            name, aggregate, aggregate_id = "ADD_TO_CART", "session", context["request_id"]
            payload = {
                "cart_id": context["request_id"],
                "cart_version": version,
                "sku": sku,
                "quantity_after": 1,
            }
        event = self.codec.build_event(
            name,
            payload,
            context
            | {
                "correlation_id": context["request_id"],
                "session_id": context["request_id"],
                "user_id": "benchmark-" + context["request_id"],
            },
            aggregate,
            aggregate_id,
            version,
            context["scheduled_at"],
            metadata={
                "dataset_revision": self.dataset_revision,
                "synthetic": True,
                "scenario_source": "benchmark",
            },
            source_service="benchmark",
        ).model_copy(
            update={
                "event_id": context["request_id"],
                "produced_at": datetime.fromisoformat(context["produced_at"]),
            }
        )
        raw, headers, topic, key = self.codec.encode(event)
        document = json.loads(raw)
        if subcase == "invalid_json":
            raw = b"{"
        elif subcase == "invalid_utf8":
            raw = b"\xff"
        elif subcase == "missing_event_id":
            del document["event_id"]
        elif subcase == "missing_payload":
            del document["payload"]
        elif subcase == "wrong_money_type":
            document["payload"]["price_minor"] = "100"
        elif subcase == "negative_quantity":
            document["payload"]["quantity_after"] = -1
        elif subcase == "unsupported_schema":
            unknown = str(max(self.codec.cache.validators) + 1).encode()
            headers = tuple(
                (name, unknown if name == "schema-id" else value) for name, value in headers
            )
        elif subcase == "unsupported_major":
            document["schema_version"] = 2
        elif subcase == "wrong_key":
            key += b":invalid"
        elif subcase == "non_utc_timestamp":
            document["event_time"] = document["event_time"].replace("Z", "+05:30")
        elif subcase is not None:
            raise ValueError("Unknown quality subcase")
        if subcase not in ("invalid_json", "invalid_utf8"):
            raw = canonical_json(document)
        return Packet(
            event.event_id,
            raw,
            topic,
            key.decode(),
            tuple((name, value.decode()) for name, value in headers),
        )
