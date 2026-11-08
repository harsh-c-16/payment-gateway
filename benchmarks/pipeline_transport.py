"""W-PIPE fixture facts use only the shared validated SDK; no operational stock writes."""

import asyncio
import os
from datetime import datetime

import httpx

from benchmarks.quality_publisher import QualityPublisher
from benchmarks.scheduler import Packet
from projectctl.providers import DependencyError
from shared.event_transport import EventCodec
from shared.event_transport.schemas import SchemaCache


class PipelineTransport:
    def __init__(self):
        self.codec = self.publisher = None
        self.skus = frozenset()
        self.revision = None
        self.namespace = None

    async def prepare(self, context, manifest, projection):
        if projection is None or not context["namespace"].startswith("bench-"):
            raise DependencyError("verified catalogue and isolated W-PIPE namespace required")
        self.revision = projection["dataset_revision"]
        self.namespace = context["namespace"]
        self.skus = frozenset(manifest["selected_skus"])
        if len(self.skus) != 10000 or not self.skus <= set(projection["active_skus"]):
            raise DependencyError("W-PIPE requires the frozen 10000 verified active SKUs")
        cache = SchemaCache.load(os.environ["EVENT_SCHEMA_CACHE_PATH"])
        with httpx.Client(
            base_url=os.environ["SCHEMA_REGISTRY_URL"], timeout=5, trust_env=False
        ) as client:
            await asyncio.to_thread(cache.verify_online, client)
        self.codec = EventCodec(cache)
        self.publisher = QualityPublisher(self.codec, os.environ["KAFKA_BOOTSTRAP_SERVERS"])

    def materialize(self, record, context):
        if self.codec is None:
            raise DependencyError("W-PIPE transport not prepared")
        value = record["payload"]
        if (
            record["expected_disposition"] != "new_valid"
            or record.get("duplicate_of") is not None
            or value.get("event_type") != "STOCK_UPDATED"
            or value.get("source_service") != "benchmark"
            or value.get("synthetic") is not True
            or value["sku"] not in self.skus
            or context["namespace"] != self.namespace
        ):
            raise ValueError("W-PIPE accepts only its frozen valid synthetic stock fixture")
        payload = {
            k: value[k]
            for k in (
                "sku",
                "stock_version",
                "on_hand",
                "reserved",
                "available",
                "order_id",
                "reservation_id",
                "reason_code",
            )
        } | {"changed_at": context["scheduled_at"]}
        event = self.codec.build_event(
            "STOCK_UPDATED",
            payload,
            {**context, "correlation_id": context["request_id"]},
            "sku",
            value["sku"],
            value["stock_version"],
            datetime.fromisoformat(context["scheduled_at"]),
            metadata={
                "dataset_revision": self.revision,
                "synthetic": True,
                "scenario_source": "benchmark",
                "padding": "",
            },
            source_service="benchmark",
        ).model_copy(
            update={
                "event_id": context["request_id"],
                "produced_at": datetime.fromisoformat(context["produced_at"]),
            }
        )
        raw, _, _, _ = self.codec.encode(event)
        target = value.get("target_event_bytes")
        if type(target) is not int or target != 1024:
            raise ValueError("W-PIPE payload target differs from the frozen recipe")
        # The envelope can itself exceed the approximate 1-KiB target. Preserve
        # it intact and record its actual bytes rather than truncating a fact.
        metadata = event.metadata.model_dump(exclude_unset=True)
        metadata["padding"] = "x" * max(0, target - len(raw))
        event = event.model_copy(update={"metadata": type(event.metadata).model_validate(metadata)})
        raw, headers, topic, key = self.codec.encode(event)
        return Packet(
            event.event_id, raw, topic, key.decode(), tuple((k, v.decode()) for k, v in headers)
        )

    async def __call__(self, packet, context):
        # Keep the raw-quality bypass unreachable from this normal workload.
        if (
            context["namespace"] != self.namespace
            or context["record"]["expected_disposition"] != "new_valid"
        ):
            raise ValueError("invalid-quality publication is not a W-PIPE operation")
        if self.publisher is None:
            raise DependencyError("W-PIPE publisher not prepared")
        return await self.publisher(packet, context)

    async def close(self):
        if self.publisher is not None:
            await self.publisher.close()
