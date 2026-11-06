"""Pure provider checks against the independent quality reasons; no broker claims."""

import json
from uuid import UUID, uuid5

import pytest

from benchmarks.quality import SUBCASES
from pipelines.ingestion.quality import QualityMaterializer
from shared.event_transport.codec import EventCodec
from shared.event_transport.schemas import RecordInvalid

from . import test_event_contracts as contracts

cache = contracts.cache
SKUS = [f"FK-EXPLICIT-FIXTURE-{number:05}" for number in range(10000)]


def context(ordinal):
    run = "00000000-0000-4000-8000-000000000001"
    return {
        "namespace": "bench-quality-provider",
        "run_id": run,
        "request_id": str(uuid5(UUID(run), f"source-{ordinal:06}")),
        "scheduled_at": "2026-11-06T10:00:00Z",
        "produced_at": "2026-11-06T10:00:00Z",
    }


def materializer(cache):
    return QualityMaterializer(
        EventCodec(cache), selected_skus=SKUS, dataset_revision="explicit-synthetic-test"
    )


def validate(cache, packet):
    return cache.validate(
        packet.body,
        tuple((name, value.encode()) for name, value in packet.headers),
        packet.channel,
        packet.key.encode(),
    )


@pytest.mark.parametrize("ordinal", [0, 9999, 10000, 98499])
def test_valid_packets_keep_frozen_identity_versions_and_provenance(cache, ordinal):
    build = materializer(cache)
    record = {"record_ordinal": ordinal, "invalid_subcase": None, "duplicate_of": None}
    packet = build(record, context(ordinal))
    assert build(record, context(ordinal)) == packet
    checked = validate(cache, packet)
    assert packet.identity == context(ordinal)["request_id"]
    assert checked.envelope.payload["sku"] == SKUS[ordinal % 10000]
    assert checked.envelope.aggregate_version == ordinal // 10000 + 1
    assert checked.envelope.source_service == "benchmark"
    assert checked.envelope.metadata.scenario_source == "benchmark"
    assert checked.envelope.metadata.dataset_revision == "explicit-synthetic-test"
    json.dumps(packet.headers)  # The scheduler journals headers as JSON text.


@pytest.mark.parametrize("subcase,reason", SUBCASES)
def test_all_independent_dirty_reasons_match_without_changing_the_oracle(cache, subcase, reason):
    ordinal = 99500 + 50 * [name for name, _ in SUBCASES].index(subcase)
    packet = materializer(cache)(
        {"record_ordinal": ordinal, "invalid_subcase": subcase, "duplicate_of": None},
        context(ordinal),
    )
    with pytest.raises(RecordInvalid) as error:
        validate(cache, packet)
    assert error.value.reason == reason


def test_duplicates_require_the_existing_scheduler_saved_packet(cache):
    with pytest.raises(ValueError, match="reuse the original persisted Packet"):
        materializer(cache)(
            {"record_ordinal": 98500, "invalid_subcase": None, "duplicate_of": 0}, context(98500)
        )


def test_invalid_selection_namespace_and_subcase_fail_closed(cache):
    for skus, revision in ((SKUS[:-1], "revision"), ([SKUS[0]] * 10000, "revision"), (SKUS, "")):
        with pytest.raises(ValueError, match="selection and revision"):
            QualityMaterializer(EventCodec(cache), selected_skus=skus, dataset_revision=revision)
    record = {"record_ordinal": 99500, "invalid_subcase": "unknown", "duplicate_of": None}
    with pytest.raises(ValueError, match="Unknown quality subcase"):
        materializer(cache)(record, context(99500))
    with pytest.raises(ValueError, match="isolated benchmark"):
        materializer(cache)(record, context(99500) | {"namespace": "dev"})
