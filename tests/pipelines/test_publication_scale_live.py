"""Publisher-only large staging fixture; not a B0/Kafka/performance or W-QUALITY run."""

import hashlib
import json
from pathlib import Path

from psycopg.types.json import Jsonb

from pipelines.curation.normalization import normalize_payload
from pipelines.ingestion import BronzeCapture
from pipelines.ingestion.receipts import persist_capture
from pipelines.storage.parquet import iter_verified
from shared.event_transport.schemas import canonical_json

from . import test_vertical_live as live
from .test_vertical_live import event, query, record

vertical = live.vertical
pytestmark = live.pytestmark


def seed_accepted_fixture(pipeline, total):
    """Real Bronze/receipts and valid snapshots; bulk SQL replaces B0 only in fixture setup."""
    with pipeline.connect() as tx, tx.transaction():
        for first in range(0, total, 256):
            values = [event(pipeline, i + 1) for i in range(first, min(first + 256, total))]
            for value in values:
                value.metadata.synthetic_padding = "x" * 1024
            sources = [record(pipeline, value, i) for i, value in enumerate(values, first)]
            receipt = BronzeCapture(pipeline.store).ingest_bronze(sources)
            assert persist_capture(tx, receipt, pipeline.store).new_sources == len(values)
            with tx.cursor().copy("""COPY silver_events(namespace,event_id,content_hash,event_time,
                event_type,source_service,aggregate_type,aggregate_id,aggregate_version,document,
                source_topic,source_partition,source_offset,raw_locator,normalized_payload)
                FROM STDIN""") as copy:
                for value, source, captured in zip(values, sources, receipt.records, strict=True):
                    document = json.loads(source.value_bytes)
                    copy.write_row(
                        (
                            value.namespace,
                            value.event_id,
                            hashlib.sha256(canonical_json(document)).hexdigest(),
                            value.event_time,
                            value.event_type,
                            value.source_service,
                            value.aggregate_type,
                            value.aggregate_id,
                            value.aggregate_version,
                            Jsonb(document),
                            source.topic,
                            source.partition,
                            source.offset,
                            captured.source.raw_locator,
                            Jsonb(normalize_payload(value)),
                        )
                    )
        tx.execute("""UPDATE source_receipts s SET disposition='new_valid',event_id=e.event_id
            FROM silver_events e WHERE s.namespace=e.namespace AND s.topic=e.source_topic
            AND s.partition=e.source_partition AND s.offset_number=e.source_offset""")
        tx.execute("INSERT INTO reducer_contributions SELECT namespace,event_id FROM silver_events")
        tx.execute("INSERT INTO export_pending SELECT namespace,event_id FROM silver_events")
        tx.execute(
            """INSERT INTO pipeline_minute
            SELECT namespace,date_trunc('minute',event_time),event_type,source_service,
            count(*),count(*),%s FROM silver_events
            GROUP BY namespace,date_trunc('minute',event_time),event_type,source_service""",
            (pipeline.transform_version,),
        )


def test_more_than_ten_thousand_facts_and_eight_mib_publish_in_bounded_files(vertical):
    seed_accepted_fixture(vertical, 10001)
    with vertical.connect() as tx:
        size = tx.execute("SELECT sum(octet_length(document::text)) FROM silver_events").fetchone()[
            0
        ]
        tx.execute("ANALYZE source_receipts")
        value = tx.execute("SELECT event_id FROM silver_events LIMIT 1").fetchone()[0]
        plan = tx.execute(
            """EXPLAIN(FORMAT JSON) SELECT * FROM source_receipts
            WHERE namespace=%s AND event_id=%s""",
            (vertical.test_namespace, value),
        ).fetchone()[0]
        assert "source_receipts_event" in json.dumps(plan)
        Path("artifacts/m08/visibility-query-plan.json").write_text(json.dumps(plan, indent=2))
    assert size > 8 * 1024 * 1024
    vertical.publish_snapshot(vertical.test_namespace)
    silver = vertical.active_manifest(vertical.test_namespace, "silver")
    assert sum(file.row_count for file in silver.files) == 10001
    assert max(file.row_count for file in silver.files) <= 512 and len(silver.files) > 1
    ids = set()
    for file in silver.files:
        for row in iter_verified(vertical.store, file):
            assert row["event_id"] not in ids
            ids.add(row["event_id"])
    assert len(ids) == query(vertical).rows[0]["unique_events"] == 10001
    with vertical.connect() as tx:
        assert tx.execute("SELECT count(*) FROM export_pending").fetchone()[0] == 0
        assert tx.execute("SELECT count(*) FROM manifest_members").fetchone()[0] == 20002
        assert (
            tx.execute(
                "SELECT count(*) FROM event_visibility WHERE observed_at IS NULL"
            ).fetchone()[0]
            == 0
        )
        assert (
            tx.execute("SELECT max(jsonb_array_length(members)) FROM observation_jobs").fetchone()[
                0
            ]
            <= 512
        )
    index = json.loads(vertical.store.read(silver.input_manifest_ids[0]))
    assert sum(part["event_count"] for part in index["membership_files"]) == 10001
    assert max(part["event_count"] for part in index["membership_files"]) <= 512
    Path("artifacts/m08/large-publisher-fixture.json").write_text(
        json.dumps(
            {
                "fixture_kind": "publisher-only synthetic SQL fixture with real Bronze/receipts",
                "code_commit": vertical.code_commit,
                "event_count": 10001,
                "document_bytes": int(size),
                "silver_file_count": len(silver.files),
                "largest_file_rows": max(f.row_count for f in silver.files),
                "gold_unique_events": 10001,
                "full_w_quality": "NOT_RUN",
                "throughput": None,
            },
            indent=2,
        )
    )
