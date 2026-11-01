"""M08 real SQL/files. Candidate construction is an explicit small compactor double."""

import hashlib
import json
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import psycopg
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import pipelines.storage.candidates as candidates
import pipelines.storage.publication as publication
from pipelines.storage.candidates import CandidateRejected
from pipelines.storage.parquet import FileVerificationError, read_verified, write_parquet
from shared.contracts.analytics import ManifestCandidate
from shared.event_transport.schemas import canonical_json

from . import test_vertical_live as live
from .test_business_gold_live import deliver, fact
from .test_vertical_live import count, curate, event, query, record

vertical = live.vertical
pytestmark = live.pytestmark


def _wire(value):
    if hasattr(value, "isoformat"):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, Decimal):
        return int(value)
    if isinstance(value, dict):
        return {k: _wire(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_wire(v) for v in value]
    return value


def candidate_double(pipeline, dataset="silver", mutate=None, declared_totals=None):
    base = pipeline.active_manifest(pipeline.test_namespace, dataset)
    groups, documents, totals = defaultdict(list), [], defaultdict(int)

    def money(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key.endswith("_minor") and item is not None and value.get("currency"):
                    totals[value["currency"]] += int(item)
                else:
                    money(item)
        elif isinstance(value, list):
            for item in value:
                money(item)

    for descriptor in base.files:
        groups[(descriptor.schema_name, tuple(sorted(descriptor.partition_values.items())))].extend(
            read_verified(pipeline.store, descriptor).to_pylist()
        )
    files = []
    prefix = f"candidate/{pipeline.test_namespace}/{uuid4()}"
    for (schema, partition), data in groups.items():
        if mutate:
            mutate(data)
        data.reverse()
        column = (
            "event_time"
            if dataset == "silver"
            else ("minute" if schema == "pipeline_minute" else "cohort_date")
        )
        files.append(
            write_parquet(
                pipeline.store,
                f"{prefix}/{len(files)}.parquet",
                data,
                schema,
                dict(partition),
                [row[column] for row in data],
            )
        )
        for row in data:
            documents.append(canonical_json([schema, 1, _wire(row)]))
            money(row)
    digest = hashlib.sha256(b"m08-logical-rows-v1\n")
    for document in sorted(documents):
        digest.update(str(len(document)).encode() + b":" + document + b"\n")
    manifest = base.model_copy(
        update={
            "generation": base.generation + 1,
            "parent_generation": base.generation,
            "files": files,
        }
    )
    return ManifestCandidate(
        base_generation=base.generation,
        candidate_manifest=manifest,
        logical_row_digest=digest.hexdigest(),
        row_count=len(documents),
        monetary_totals_by_currency=dict(totals) if declared_totals is None else declared_totals,
        transformation_reason="explicit-test-compactor",
    )


def test_incremental_chunks_preserve_gapped_membership_and_reuse_silver(vertical, monkeypatch):
    monkeypatch.setattr(publication, "FILE_MAX_ROWS", 2)
    values = [event(vertical, v) for v in range(1, 6)]
    sources = [
        record(vertical, value, offset)
        for value, offset in zip(values, [0, 2, 4, 7, 10], strict=True)
    ]
    assert curate(vertical, sources).new_valid == 5
    vertical.publish_snapshot(vertical.test_namespace)
    first = vertical.active_manifest(vertical.test_namespace, "silver")
    assert sorted(file.row_count for file in first.files) == [1, 2, 2]
    old_paths = {file.path for file in first.files}
    original, converted = publication._silver_row, []

    def tracked(row):
        converted.append(str(row["event_id"]))
        return original(row)

    monkeypatch.setattr(publication, "_silver_row", tracked)
    newest = event(vertical, 6)
    curate(vertical, [record(vertical, newest, 15)])
    vertical.publish_snapshot(vertical.test_namespace)
    second = vertical.active_manifest(vertical.test_namespace, "silver")
    assert old_paths < {file.path for file in second.files}
    assert converted == [newest.event_id]
    assert sum(file.row_count for file in second.files) == 6
    assert query(vertical).rows[0]["unique_events"] == 6
    index = json.loads(vertical.store.read(second.input_manifest_ids[0]))
    assert index["parent_input_manifest_ids"] == first.input_manifest_ids
    part = json.loads(vertical.store.read(index["membership_files"][0]["path"]))
    assert part["event_ids"] == [newest.event_id] and part["sources"][0]["offset_number"] == 15
    assert second.source_ranges[0].first_offset == 0 and second.source_ranges[0].next_offset == 16
    with vertical.connect() as tx:
        assert (
            tx.execute(
                "SELECT count(*) FROM manifest_members WHERE dataset='gold' AND generation=2"
            ).fetchone()[0]
            == 1
        )
        assert set(publication.iter_membership(tx, vertical.test_namespace, "gold", 2)) == {
            value.event_id for value in [*values, newest]
        }


@pytest.mark.parametrize("dataset", ["silver", "gold"])
def test_candidate_reorders_rows_and_preserves_paired_generations_visibility_and_old_files(
    vertical, dataset, monkeypatch
):
    monkeypatch.setattr(publication, "FILE_MAX_ROWS", 1)
    curate(vertical, [record(vertical, event(vertical, i), i - 1) for i in range(1, 4)])
    vertical.publish_snapshot(vertical.test_namespace)
    old = {d: vertical.active_manifest(vertical.test_namespace, d) for d in ("silver", "gold")}
    candidate = candidate_double(vertical, dataset)
    assert vertical.publish_candidate(candidate).generation == 2
    assert all(vertical.active_manifest(vertical.test_namespace, d).generation == 2 for d in old)
    assert query(vertical).rows[0]["unique_events"] == 3
    assert count(vertical, "export_pending") == 0
    for manifest in old.values():
        assert all(read_verified(vertical.store, f).num_rows == f.row_count for f in manifest.files)
    with vertical.connect() as tx:
        assert (
            tx.execute("SELECT count(*) FROM manifest_members WHERE generation=2").fetchone()[0]
            == 0
        )
        assert all(
            len(list(publication.iter_membership(tx, vertical.test_namespace, d, 2))) == 3
            for d in old
        )
        assert tx.execute(
            "SELECT min(generation),max(generation) FROM event_visibility"
        ).fetchone() == (1, 1)


@pytest.mark.parametrize(
    "kind",
    [
        "changed_row",
        "duplicate",
        "namespace",
        "count",
        "digest",
        "money",
        "bounds",
        "checksum",
        "schema",
        "partition",
        "reuse",
        "transform",
        "lineage",
        "parent",
    ],
)
def test_bad_candidates_never_change_active_state(vertical, kind):
    curate(vertical, [record(vertical, event(vertical))])
    vertical.publish_snapshot(vertical.test_namespace)

    def mutate(rows):
        if kind == "changed_row":
            rows[0]["payload"]["duration_ms"] = 99.0
        elif kind == "duplicate":
            rows.append(dict(rows[0]))
        elif kind == "namespace":
            rows[0]["namespace"] = "bench-foreign"

    candidate = candidate_double(vertical, mutate=mutate)
    if kind in {"count", "digest", "money"}:
        field, value = {
            "count": ("row_count", 9),
            "digest": ("logical_row_digest", "0" * 64),
            "money": ("monetary_totals_by_currency", {"INR": 1}),
        }[kind]
        candidate = candidate.model_copy(update={field: value})
    elif kind in {"transform", "lineage", "parent"}:
        field, value = {
            "transform": ("transform_version", "changed-transform"),
            "lineage": ("input_manifest_ids", []),
            "parent": ("parent_generation", None),
        }[kind]
        candidate.candidate_manifest = candidate.candidate_manifest.model_copy(
            update={field: value}
        )
    elif kind in {"bounds", "checksum", "schema", "partition", "reuse"}:
        file = candidate.candidate_manifest.files[0]
        if kind == "bounds":
            file = file.model_copy(
                update={
                    "min_event_time": file.min_event_time + timedelta(days=1),
                    "max_event_time": file.max_event_time + timedelta(days=1),
                }
            )
        elif kind == "reuse":
            file = vertical.active_manifest(vertical.test_namespace, "silver").files[0]
        else:
            field, value = {
                "checksum": ("sha256", "0" * 64),
                "schema": ("schema_version", 2),
                "partition": ("partition_values", {"event_date": "2026-01-01"}),
            }[kind]
            file = file.model_copy(update={field: value})
        candidate.candidate_manifest.files = [file]
    with pytest.raises((CandidateRejected, FileVerificationError)):
        vertical.publish_candidate(candidate)
    assert vertical.active_manifest(vertical.test_namespace, "gold").generation == 1
    assert query(vertical).rows[0]["unique_events"] == 1 and count(vertical, "export_pending") == 0


def test_stale_candidate_is_rejected_before_reading_files(vertical, monkeypatch):
    curate(vertical, [record(vertical, event(vertical))])
    vertical.publish_snapshot(vertical.test_namespace)
    candidate = candidate_double(vertical)
    curate(vertical, [record(vertical, event(vertical, 2), 1)])
    vertical.publish_snapshot(vertical.test_namespace)

    def unexpected(*args):
        pytest.fail("Stale candidates must not read files")

    monkeypatch.setattr(candidates, "_stage", unexpected)
    with pytest.raises(publication.PublicationConflict, match="STALE_MANIFEST"):
        vertical.publish_candidate(candidate)
    assert query(vertical).rows[0]["unique_events"] == 2


def test_candidate_uses_published_rows_and_retains_new_ingress(vertical, monkeypatch):
    curate(vertical, [record(vertical, event(vertical))])
    vertical.publish_snapshot(vertical.test_namespace)
    candidate = candidate_double(vertical, "gold")
    original = candidates._stage

    def incoming(pipeline, tx, manifest, side):
        result = original(pipeline, tx, manifest, side)
        if side == "base":
            curate(vertical, [record(vertical, event(vertical, 2), 1)])
        return result

    monkeypatch.setattr(candidates, "_stage", incoming)
    vertical.publish_candidate(candidate)
    assert query(vertical).generation == 2 and query(vertical).rows[0]["unique_events"] == 1
    assert count(vertical, "export_pending") == 1
    assert vertical.publish_snapshot(vertical.test_namespace).generation == 3
    assert query(vertical).rows[0]["unique_events"] == 2 and count(vertical, "export_pending") == 0


def test_exact_money_and_int64_candidate_contract_are_not_coerced(vertical):
    deliver(vertical, fact(vertical, "ORDER_CONFIRMED", total_amount_minor=12345))
    vertical.publish_snapshot(vertical.test_namespace)
    candidate = candidate_double(vertical, "gold")
    # Integrity sum: order amount plus daily created and confirmed amounts.
    assert candidate.monetary_totals_by_currency == {"INR": 37035}
    vertical.publish_candidate(candidate)
    deliver(vertical, fact(vertical, "ORDER_CONFIRMED", 2, total_amount_minor=2**63 - 1))
    vertical.publish_snapshot(vertical.test_namespace)
    oversized = candidate_double(vertical, "gold", declared_totals={"INR": 0})
    with pytest.raises(CandidateRejected, match="int64 contract"):
        vertical.publish_candidate(oversized)
    assert vertical.active_manifest(vertical.test_namespace, "gold").generation == 3


def test_candidate_pointer_failure_rolls_back_both_generations(vertical):
    curate(vertical, [record(vertical, event(vertical))])
    vertical.publish_snapshot(vertical.test_namespace)
    candidate = candidate_double(vertical)
    with vertical.connect() as tx:
        tx.execute("""CREATE FUNCTION m08_pointer_failure() RETURNS trigger LANGUAGE plpgsql
            AS $$ BEGIN IF NEW.dataset='gold' THEN RAISE EXCEPTION 'explicit candidate failure';
            END IF; RETURN NEW; END $$""")
        tx.execute("""CREATE TRIGGER m08_pointer_failure BEFORE INSERT OR UPDATE ON active_datasets
            FOR EACH ROW EXECUTE FUNCTION m08_pointer_failure()""")
    with pytest.raises(psycopg.Error, match="explicit candidate failure"):
        vertical.publish_candidate(candidate)
    assert all(
        vertical.active_manifest(vertical.test_namespace, d).generation == 1
        for d in ("silver", "gold")
    )
    assert query(vertical).rows[0]["unique_events"] == 1


def test_candidate_rechecks_generation_at_actual_pointer_transaction(vertical, monkeypatch):
    curate(vertical, [record(vertical, event(vertical))])
    vertical.publish_snapshot(vertical.test_namespace)
    candidate = candidate_double(vertical)
    original = publication.activate

    def external_advance(tx, namespace, old, manifests):
        # Explicit external-writer fixture bypasses the session lock to exercise the CAS itself.
        with vertical.connect() as other, other.transaction():
            advanced = {
                d: m.model_copy(update={"generation": 2, "parent_generation": 1})
                for d, m in old.items()
            }
            original(other, namespace, old, advanced)
            other.execute("""INSERT INTO manifest_members SELECT namespace,dataset,2,event_id
                FROM manifest_members WHERE generation=1""")
        original(tx, namespace, old, manifests)

    monkeypatch.setattr(publication, "activate", external_advance)
    with pytest.raises(publication.PublicationConflict, match="STALE_MANIFEST"):
        vertical.publish_candidate(candidate)
    assert query(vertical).generation == 2 and query(vertical).rows[0]["unique_events"] == 1


@pytest.mark.parametrize("kind", ["codec", "row_group"])
def test_candidate_physical_file_guards(vertical, kind):
    curate(vertical, [record(vertical, event(vertical))])
    vertical.publish_snapshot(vertical.test_namespace)
    candidate = candidate_double(vertical)
    file = candidate.candidate_manifest.files[0]
    table = read_verified(vertical.store, file)
    if kind == "row_group":
        rows = table.to_pylist()
        rows[0]["envelope_json"] = "x" * (33 * 1024 * 1024)
        table = pa.Table.from_pylist(rows, schema=table.schema)
    sink = pa.BufferOutputStream()
    pq.write_table(table, sink, compression="snappy" if kind == "codec" else "zstd")
    raw = sink.getvalue().to_pybytes()
    new = vertical.store.write_immutable(file.path + ".guard", raw, hashlib.sha256(raw).hexdigest())
    candidate.candidate_manifest.files = [
        file.model_copy(update={"path": new.path, "sha256": new.sha256, "byte_size": new.byte_size})
    ]
    with pytest.raises((CandidateRejected, FileVerificationError)):
        vertical.publish_candidate(candidate)
    assert query(vertical).generation == 1


def test_compaction_lineage_retains_historical_transform(vertical):
    current = vertical.transform_version
    vertical.transform_version = "historical-transform"
    curate(vertical, [record(vertical, event(vertical))])
    vertical.publish_snapshot(vertical.test_namespace)
    vertical.transform_version = current
    candidate = candidate_double(vertical)
    active = vertical.publish_candidate(candidate)
    lineage = json.loads(vertical.store.read(active.input_manifest_ids[0]))
    assert active.transform_version == "historical-transform"
    assert lineage["transform_version"] == active.transform_version
