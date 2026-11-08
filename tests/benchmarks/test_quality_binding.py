"""Explicit transport/registry doubles; these checks are never a live G1/T-03."""

import asyncio
import base64
import copy
import hashlib
import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from benchmarks.quality import SUBCASES
from benchmarks.quality_audit import fixture_rows, read_jsonl, reconcile_quality
from benchmarks.quality_binding import QualityLifecycle, QualityOwners, build_quality_bindings
from benchmarks.quality_publisher import QualityDriver, QualityPublisher, RawFixturePublisher
from benchmarks.scheduler import Limits, run_schedule
from pipelines.ingestion.quality import QualityMaterializer
from projectctl.artifacts import canonical_json
from projectctl.config import load_config
from projectctl.providers import DependencyError, ProviderRegistry
from shared.event_transport.codec import EventCodec
from shared.event_transport.consumer import raw_fingerprint
from shared.event_transport.publisher import PRODUCER_SETTINGS
from shared.event_transport.schemas import SchemaCache, documents

SKUS = [f"FK-OFFLINE-DOUBLE-{i:05}" for i in range(10000)]


@pytest.fixture
def codec():
    # Explicit offline registry IDs; never loaded by production composition.
    return EventCodec(
        SchemaCache(
            {
                "compatibility": "BACKWARD_TRANSITIVE",
                "schemas": [
                    {**entry, "id": number, "version": 1, "schema": schema}
                    for number, (entry, schema) in enumerate(documents().values(), 101)
                ],
            }
        )
    )


def context(tmp_path):
    return {
        "run_id": "00000000-0000-4000-8000-000000000001",
        "namespace": "bench-quality-offline",
        "seed": 42,
        "selected_skus": SKUS,
        "dataset_revision": "explicit-test-double",
        "evidence_directory": str(tmp_path),
        "scheduled_at": "2026-11-07T10:00:00Z",
        "produced_at": "2026-11-07T10:00:00Z",
        "request_id": "00000000-0000-4000-8000-000000000002",
    }


class NormalDouble:
    def __init__(self):
        self.calls = []

    def publish_event(self, event, topic, key):
        self.calls.append(event.event_id)
        return SimpleNamespace(
            event_id=event.event_id, topic=topic, partition=0, offset=len(self.calls) - 1
        )

    def close(self):
        pass


class RawDouble:
    def __init__(self):
        self.calls = []

    def publish(self, packet):
        self.calls.append(packet)
        return dict(topic=packet.channel, partition=0, offset=len(self.calls) - 1)

    def close(self):
        pass


@pytest.mark.parametrize("subcase,reason", SUBCASES)
def test_only_independent_invalid_cases_can_use_raw(codec, tmp_path, subcase, reason):
    ctx = context(tmp_path)
    record = dict(
        record_ordinal=99500 + 50 * [name for name, _ in SUBCASES].index(subcase),
        duplicate_of=None,
        expected_disposition="invalid",
        invalid_subcase=subcase,
        reason_code=reason,
    )
    packet = QualityMaterializer(
        codec, selected_skus=SKUS, dataset_revision=ctx["dataset_revision"]
    )(record, ctx)
    normal, raw = NormalDouble(), RawDouble()
    publisher = QualityPublisher(codec, "offline-double", normal=normal, raw=raw)
    receipt = asyncio.run(publisher(packet, ctx | {"record": record}))
    assert len(raw.calls) == 1 and normal.calls == []
    assert receipt.source["topic"] == packet.channel
    assert receipt.identity == packet.identity
    # Relabelling dirty bytes as normal cannot bypass SDK validation.
    with pytest.raises(ValueError, match="normal quality event"):
        asyncio.run(
            publisher(packet, ctx | {"record": record | {"expected_disposition": "new_valid"}})
        )


def test_normal_events_never_use_raw_and_concurrent_duplicates_are_physical(codec, tmp_path):
    ctx = context(tmp_path)
    row = next(fixture_rows(42))
    packet = QualityMaterializer(
        codec, selected_skus=SKUS, dataset_revision=ctx["dataset_revision"]
    )(row, ctx)
    normal, raw = NormalDouble(), RawDouble()
    publisher = QualityPublisher(codec, "offline-double", normal=normal, raw=raw)

    async def send():
        return await asyncio.gather(*(publisher(packet, ctx | {"record": row}) for _ in range(3)))

    receipts = asyncio.run(send())
    assert normal.calls == [packet.identity] * 3 and raw.calls == []
    assert {r.source["offset"] for r in receipts} == {0, 1, 2}
    with pytest.raises(ValueError, match="independent invalid"):
        asyncio.run(
            publisher(
                packet,
                ctx
                | {
                    "record": row
                    | {
                        "expected_disposition": "invalid",
                        "invalid_subcase": "invalid_json",
                        "reason_code": "INVALID_JSON",
                    }
                },
            )
        )


def test_raw_publisher_preserves_frozen_settings_and_exact_bytes(codec, tmp_path):
    ctx = context(tmp_path)
    row = list(fixture_rows(42, "G1"))[-1]
    packet = QualityMaterializer(
        codec, selected_skus=SKUS, dataset_revision=ctx["dataset_revision"]
    )(row, ctx)
    calls = []

    class ProducerDouble:
        def __init__(self, settings):
            assert settings == {**PRODUCER_SETTINGS, "bootstrap.servers": "double"}

        def produce(self, topic, **kwargs):
            calls.append((topic, kwargs))
            self.callback = kwargs["on_delivery"]

        def poll(self, timeout):
            self.callback(
                None,
                SimpleNamespace(
                    topic=lambda: packet.channel, partition=lambda: 0, offset=lambda: 7
                ),
            )

        def flush(self, timeout):
            return 0

    raw = RawFixturePublisher("double", producer_factory=ProducerDouble)
    assert raw.producer is None
    assert raw.publish(packet)["offset"] == 7
    assert calls[0][1]["value"] == packet.body
    assert calls[0][1]["headers"] == [(n, v.encode()) for n, v in packet.headers]
    raw.close()


def make_g1_evidence(tmp_path, codec):
    ctx = context(tmp_path)
    planned = [
        row
        | {"phase": "measurement", "scenario_id": row["logical_record_id"], "offset_seconds": None}
        for row in fixture_rows(42, "G1")
    ]
    path = tmp_path / "planned.jsonl"
    path.write_bytes(b"".join(canonical_json(row) + b"\n" for row in planned))
    build = QualityMaterializer(codec, selected_skus=SKUS, dataset_revision=ctx["dataset_revision"])
    sent = []

    async def publish_double(packet, local):
        from benchmarks.scheduler import Receipt

        sent.append(packet)
        return Receipt(
            packet.identity,
            "accepted",
            source=dict(topic=packet.channel, partition=0, offset=len(sent) - 1),
        )

    driver = QualityDriver(publish_double)
    driver.materializer = build
    asyncio.run(
        run_schedule(
            path,
            tmp_path,
            driver,
            ctx,
            kind="finite",
            warmup_seconds=0,
            duration_seconds=1,
            drain_seconds=5,
            limits=Limits(1, 10),
        )
    )
    assert sent[0] == sent[1]  # Persisted identity, bytes, topic, key and headers.
    receipts, bronze, invalid = [], [], []
    emissions = read_jsonl(tmp_path / "emissions.jsonl")
    for row, packet, emission in zip(planned, sent, emissions, strict=True):
        source = emission["source"]
        digest = raw_fingerprint(
            packet.key.encode(),
            packet.body,
            tuple((name, value.encode()) for name, value in packet.headers),
        )
        receipt = dict(
            namespace=ctx["namespace"],
            source=source,
            raw_sha256=digest,
            event_id=packet.identity if row["expected_disposition"] != "invalid" else None,
            disposition=row["expected_disposition"],
            reason_code=row["reason_code"],
            gold_visible_at=None,
            silver_committed_observed_at=None,
        )
        receipts.append(receipt)
        bronze.append(
            dict(
                source=source,
                value_base64=base64.b64encode(packet.body).decode(),
                key_base64=base64.b64encode(packet.key.encode()).decode(),
                headers=[list(pair) for pair in packet.headers],
            )
        )
        if row["expected_disposition"] == "invalid":
            invalid.append(
                dict(
                    namespace=ctx["namespace"],
                    source_locator=source,
                    raw_sha256=digest,
                    reason_code=row["reason_code"],
                )
            )
    document = json.loads(sent[0].body)
    silver = dict(
        event_id=sent[0].identity,
        content_hash=hashlib.sha256(canonical_json(document)).hexdigest(),
        namespace=ctx["namespace"],
        envelope_json=sent[0].body.decode(),
        payload=document["payload"],
    )
    minute = datetime.fromisoformat(document["event_time"]).replace(second=0, microsecond=0)
    observed = dict(
        namespace=ctx["namespace"],
        run_id=ctx["run_id"],
        test_mode="stub",
        collection_complete=True,
        receipts=receipts,
        bronze=bronze,
        quarantine=invalid,
        silver=[silver],
        offsets=[
            dict(topic=sent[0].channel, partition=0, committed_next_offset=3, log_end_next_offset=3)
        ],
        gold=dict(
            generation=1,
            query_generation=1,
            manifest_sha256="a" * 64,
            query_manifest_sha256="a" * 64,
            membership_ids=[sent[0].identity],
            rows=[
                dict(
                    namespace=ctx["namespace"],
                    minute=minute.isoformat(),
                    event_type="STOCK_UPDATED",
                    source_service="benchmark",
                    unique_events=1,
                )
            ],
        ),
        sink_batches=[
            {
                "namespace": ctx["namespace"],
                "run_id": ctx["run_id"],
                "replay_id": None,
                "batch_sequence": i + 1,
                "batch_rows": 1,
                "sources": [row["source"]],
                "flush_duration_seconds": None,
                **{
                    name: int(row["disposition"] == name)
                    for name in ("new_valid", "duplicate_delivery", "invalid", "redelivery_noop")
                },
            }
            for i, row in enumerate(receipts)
        ],
    )
    return ctx, observed


def test_g1_oracle_and_scheduler_reuse_saved_packet(tmp_path, codec):
    ctx, observed = make_g1_evidence(tmp_path, codec)
    result = reconcile_quality(ctx, tmp_path, observed, gate="G1")
    assert result["status"] == "PASS", result
    assert result["physical_deliveries"] == 3 and result["logical_events"] == 1
    assert result["timings"] == {"status": "NOT_RUN", "value": None}
    # The same three rows can never pass the 100,000-record T-03 gate.
    result = reconcile_quality(ctx, tmp_path, observed)
    assert result["passed"] is False


def test_real_arrow_payload_shape_preserves_sparse_stock_expectations(tmp_path, codec):
    import pyarrow as pa

    from benchmarks.quality_sources import json_value
    from pipelines.storage.parquet import PAYLOAD_TYPE

    ctx, observed = make_g1_evidence(tmp_path, codec)
    payload = dict(observed["silver"][0]["payload"])
    payload["changed_at"] = datetime.fromisoformat(payload["changed_at"])
    # Real declared Arrow type, explicit synthetic values, no production cleaner.
    observed["silver"][0]["payload"] = json_value(
        pa.array([payload], type=PAYLOAD_TYPE).to_pylist()[0]
    )
    assert reconcile_quality(ctx, tmp_path, observed, gate="G1")["passed"] is True
    observed["silver"][0]["payload"]["price_minor"] = 1
    assert reconcile_quality(ctx, tmp_path, observed, gate="G1")["passed"] is False


@pytest.mark.parametrize(
    "fault",
    [
        "missing_receipt",
        "extra_source",
        "changed_bronze",
        "wrong_reason",
        "silver_payload",
        "silver_hash",
        "extra_gold",
        "wrong_gold_total",
        "stale_generation",
        "missing_offset",
        "uncommitted",
        "missing_quarantine",
        "duplicate_receipt",
        "plan_label",
        "missing_sink_batch",
        "bad_sink_scope",
        "body_hash_as_source_fingerprint",
        "wrong_batch_disposition",
    ],
)
def test_independent_oracle_rejects_wrong_evidence(tmp_path, codec, fault):
    ctx, observed = make_g1_evidence(tmp_path, codec)
    if fault == "missing_receipt":
        observed["receipts"].pop()
    elif fault == "extra_source":
        extra = copy.deepcopy(observed["receipts"][0])
        extra["source"]["offset"] = 100
        observed["receipts"].append(extra)
    elif fault == "changed_bronze":
        observed["bronze"][0]["value_base64"] = "e30="
    elif fault == "wrong_reason":
        observed["receipts"][-1]["reason_code"] = "INVALID_TYPE"
    elif fault == "silver_payload":
        observed["silver"][0]["payload"] = {"available": 999}
    elif fault == "silver_hash":
        observed["silver"][0]["content_hash"] = "b" * 64
    elif fault == "extra_gold":
        observed["gold"]["membership_ids"].append("unexpected")
    elif fault == "wrong_gold_total":
        observed["gold"]["rows"][0]["unique_events"] = 2
    elif fault == "stale_generation":
        observed["gold"]["query_generation"] = 2
    elif fault == "missing_offset":
        observed["offsets"] = []
    elif fault == "uncommitted":
        observed["offsets"][0]["committed_next_offset"] = 2
    elif fault == "missing_quarantine":
        observed["quarantine"] = []
    elif fault == "duplicate_receipt":
        observed["receipts"].append(observed["receipts"][0])
    elif fault == "missing_sink_batch":
        observed["sink_batches"].pop()
    elif fault == "bad_sink_scope":
        observed["sink_batches"][0]["namespace"] = "bench-other"
    elif fault == "body_hash_as_source_fingerprint":
        observed["receipts"][0]["raw_sha256"] = read_jsonl(tmp_path / "emissions.jsonl")[0][
            "wire_sha256"
        ]
    elif fault == "wrong_batch_disposition":
        observed["sink_batches"][0].update(new_valid=0, duplicate_delivery=1)
    else:
        planned = read_jsonl(tmp_path / "planned.jsonl")
        planned[0]["expected_disposition"] = "invalid"
        (tmp_path / "planned.jsonl").write_bytes(
            b"".join(canonical_json(row) + b"\n" for row in planned)
        )
    assert reconcile_quality(ctx, tmp_path, observed, gate="G1")["passed"] is False


def test_missing_collection_or_real_review_is_incomplete(tmp_path, codec):
    ctx, observed = make_g1_evidence(tmp_path, codec)
    observed["test_mode"] = "real"
    assert reconcile_quality(ctx, tmp_path, observed, gate="G1")["passed"] is None
    observed.update(binding_review_verified=True, collection_complete=False)
    assert reconcile_quality(ctx, tmp_path, observed, gate="G1")["status"] == "INCOMPLETE"


def test_missing_quality_dependencies_are_explicit_and_start_no_transport(tmp_path):
    binding = build_quality_bindings(load_config(), owners=QualityOwners())
    assert binding.mode == "real" and binding.driver.materializer is None
    assert any("manifests unavailable" in reason for reason in binding.dependency_reasons)
    assert any("review_path unavailable" in reason for reason in binding.dependency_reasons)
    with pytest.raises(DependencyError, match="callbacks or manifests missing"):
        asyncio.run(binding.prepare(context(tmp_path), {}))


def test_quality_registration_composes_existing_providers_without_duplicates():
    from benchmarks.quality_binding import register

    registry = ProviderRegistry()
    register(registry)
    assert registry.availability()["workloads"]["W-QUALITY"] is True
    assert registry.workload("W-QUALITY", load_config()).dependency_reasons


def test_partial_quality_recipe_cannot_validate_as_full_trial(tmp_path):
    lifecycle = QualityLifecycle(load_config(), QualityOwners(), {})
    lifecycle.publisher = object()

    class SourcesDouble:
        def receipt_rows(self, namespace):
            return []

    lifecycle.sources = SourcesDouble()
    with pytest.raises(DependencyError, match="100000-record"):
        asyncio.run(lifecycle.validate(context(tmp_path), {"expected_counts": {"planned": 3}}))
