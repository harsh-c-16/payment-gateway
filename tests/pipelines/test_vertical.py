"""Offline boundary checks. The byte-store double makes no filesystem durability claim."""

import hashlib
from datetime import UTC, datetime

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from pydantic import ValidationError

from pipelines.curation import BatchConfig
from pipelines.gold import aggregate_gold
from pipelines.ingestion.runtime import pipeline_from_env
from pipelines.storage.parquet import (
    GOLD_SCHEMA,
    FileVerificationError,
    read_verified,
    write_parquet,
)
from shared.contracts.analytics import FileDescriptor


@pytest.mark.parametrize("rows", [True, False, 0, 2, 101, "1"])
def test_sink_rejects_unsupported_or_coerced_batch_rows(rows):
    with pytest.raises(ValidationError):
        BatchConfig.model_validate({"run_id": "explicit-fixture", "sink_batch_max_rows": rows})


def test_runtime_rejects_unpinned_commit_and_unsupported_batching(monkeypatch):
    monkeypatch.setenv("CODE_COMMIT", "unknown")
    with pytest.raises(ValueError, match="actual"):
        pipeline_from_env()
    monkeypatch.setenv("SINK_BATCH_MAX_ROWS", "2")
    with pytest.raises(ValueError, match="B0"):
        pipeline_from_env()


@pytest.mark.parametrize("rows", [1, 100])
def test_b0_and_o1_are_explicit_supported_groupings(rows):
    assert (
        BatchConfig(run_id="explicit-fixture", sink_batch_max_rows=rows).sink_batch_max_rows == rows
    )


def test_typed_parquet_zstd_utc_hash_and_count_boundaries():
    class ByteStoreDouble:
        def write_immutable(self, path, data, sha256):
            assert hashlib.sha256(data).hexdigest() == sha256
            self.data = data
            return FileDescriptor(
                path=path,
                sha256=sha256,
                byte_size=len(data),
                row_count=0,
                schema_name="opaque-bytes",
                schema_version=1,
                partition_values={},
                min_event_time=None,
                max_event_time=None,
            )

        def read(self, path):
            return self.data

    store = ByteStoreDouble()
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    row = {
        "namespace": "bench-fixture",
        "minute": now,
        "event_type": "CONVERSATION_TURN",
        "source_service": "conversation",
        "unique_events": 1,
        "transform_version": "m05-conversation-v1",
        "revision": 1,
        "publication_generation": 1,
    }
    descriptor = write_parquet(store, "gold/file.parquet", [row], "pipeline_minute", {}, [now])
    assert read_verified(store, descriptor).schema == GOLD_SCHEMA
    assert read_verified(store, descriptor).to_pylist() == [row]
    assert (
        pq.read_metadata(pa.BufferReader(store.data)).row_group(0).column(0).compression == "ZSTD"
    )
    with pytest.raises(FileVerificationError):
        read_verified(store, descriptor.model_copy(update={"row_count": 2}))
    store.data = b"corrupted"
    with pytest.raises(FileVerificationError):
        read_verified(store, descriptor)


def test_gold_reducer_rejects_idle_caller_before_writes():
    from types import SimpleNamespace

    from psycopg.pq import TransactionStatus

    idle = SimpleNamespace(info=SimpleNamespace(transaction_status=TransactionStatus.IDLE))
    with pytest.raises(ValueError, match="caller-owned"):
        aggregate_gold([], idle)
