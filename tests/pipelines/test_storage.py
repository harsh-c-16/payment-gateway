"""Real filesystem tests; syscall failures are explicit injected fault cases."""

import errno
import hashlib
import json
import os
import stat
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

import pipelines.ingestion.bronze as bronze
import pipelines.storage as storage
from pipelines.ingestion import BronzeCapture, CaptureTooLarge, SourceCorruption, read_bronze
from pipelines.storage import DurabilityUnavailable, FileStore, ImmutableConflict
from shared.contracts.events import SourceRecord
from shared.event_transport.consumer import ConsumerGroup, raw_fingerprint

from .transport_doubles import ConsumerDouble, MessageDouble

POSIX = pytest.mark.skipif(os.name != "posix", reason="Real directory fsync requires POSIX")


@pytest.fixture
def store(tmp_path):
    if os.name != "posix":
        pytest.skip("Real Linux volume required; no fake Windows durability")
    root = Path(os.environ.get("LAKEHOUSE_ROOT", tmp_path)) / ("test-" + uuid4().hex)
    root.mkdir()
    return FileStore(root)


def source(offset=0, value=b"\xff{invalid", key=None, headers=(("x", None), ("x", b""))):
    return SourceRecord(
        "bench-m04",
        "bench-m04.conversation-events.v1",
        0,
        offset,
        key,
        value,
        headers,
        None,
        datetime.now(UTC),
        raw_fingerprint(key, value, headers),
        "runtime-ownership",
    )


def write(store, path="raw/archive.bin", data=b"exact\x00\xff\nbytes"):
    return store.write_immutable(path, data, hashlib.sha256(data).hexdigest())


def test_native_windows_fails_before_writing(tmp_path):
    if os.name == "posix":
        pytest.skip("Windows-only unsupported-filesystem check")
    with pytest.raises(DurabilityUnavailable):
        FileStore(tmp_path)
    assert not list(tmp_path.iterdir())


def test_opaque_archive_hash_idempotency_and_orphan_inventory(store):
    descriptor = write(store)
    assert store.read(descriptor.path) == b"exact\x00\xff\nbytes"
    assert descriptor.row_count == 0 and descriptor.schema_name == "opaque-bytes"
    assert descriptor == write(store)
    assert store.exists_with_hash(descriptor.path, descriptor.sha256)
    assert not store.exists_with_hash("absent.bin", descriptor.sha256)
    assert store.list_orphans({descriptor.path}) == []
    assert store.list_orphans(set()) == [descriptor.path]
    assert store.read(descriptor.path)  # inventory never deletes anything
    with pytest.raises(ImmutableConflict):
        write(store, data=b"changed")
    with pytest.raises(ValueError, match="SHA-256"):
        store.write_immutable("bad.bin", b"data", "0" * 64)
    assert not (store.root / "bad.bin").exists()


@pytest.mark.parametrize(
    "path",
    [
        "../escape",
        "/absolute",
        "a/../b",
        "a//b",
        "a/./b",
        "C:/drive",
        "a\\b",
        ".filestore.lock",
        "",
    ],
)
def test_paths_cannot_escape_or_address_internal_lock(store, path):
    with pytest.raises(ValueError):
        write(store, path)


def test_symlink_escape_rejected(store, tmp_path):
    (store.root / "link").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        write(store, "link/escape")
    with pytest.raises(ValueError, match="symlink"):
        store.list_orphans(set())


def test_concurrent_writers_cannot_replace_immutable_winner(store):
    def attempt(data):
        try:
            return write(FileStore(store.root), "race.bin", data).sha256
        except ImmutableConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, (b"first", b"second")))
    assert results.count("conflict") == 1
    assert hashlib.sha256(store.read("race.bin")).hexdigest() in results


def test_directory_fsync_failure_after_rename_is_visible_and_retryable(store, monkeypatch):
    real = storage.sync_directory

    def fail_after_rename(path):
        if (store.root / "result.bin").exists():
            raise OSError(errno.EIO, "explicit directory-fsync fault")
        real(path)

    monkeypatch.setattr(storage, "sync_directory", fail_after_rename)
    with pytest.raises(OSError):
        write(store, "result.bin")
    assert store.list_orphans(set()) == ["result.bin"]
    monkeypatch.setattr(storage, "sync_directory", real)
    assert write(store, "result.bin").byte_size > 0


def test_disk_full_before_rename_never_returns_capture_or_offsets(store, monkeypatch):
    topic = "bench-m04.conversation-events.v1"
    worker = ConsumerGroup(
        "bench-m04.analytics.v1", [topic], "explicit-double", consumer_factory=ConsumerDouble
    )
    worker.consumer.messages.append(MessageDouble(topic, 0))
    records = worker.consume_records([topic], 1, 20)

    def full(*args):
        raise OSError(errno.ENOSPC, "explicit full-disk fault")

    monkeypatch.setattr(storage.os, "replace", full)
    with pytest.raises(OSError):
        BronzeCapture(store).ingest_bronze(records)
    assert worker.durable_next_offsets() == {}
    assert not worker.commit_offsets({(topic, 0): 1}).succeeded
    assert not worker.consumer.commits
    assert store.list_orphans(set()) == []
    worker.close()


def test_file_fsync_failure_leaves_no_completed_file(store, monkeypatch):
    real = storage.os.fsync

    def full(descriptor):
        if stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError(errno.ENOSPC, "explicit file-fsync fault")
        real(descriptor)

    monkeypatch.setattr(storage.os, "fsync", full)
    with pytest.raises(OSError):
        write(store)
    assert store.list_orphans(set()) == []


def test_process_crash_after_rename_leaves_recoverable_orphan(store):
    script = """
import os, sys, hashlib
import pipelines.storage as storage
from pathlib import Path
root = Path(sys.argv[1])
original = storage.sync_directory
def crash(path):
    if (root / 'crash.bin').exists():
        print('M04_AFTER_RENAME_BARRIER_ACK', flush=True)
        os._exit(73)
    original(path)
storage.sync_directory = crash
storage.FileStore(root).write_immutable('crash.bin', b'exact', hashlib.sha256(b'exact').hexdigest())
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(store.root)], capture_output=True, text=True, timeout=20
    )
    assert completed.returncode == 73
    assert "M04_AFTER_RENAME_BARRIER_ACK" in completed.stdout
    assert store.list_orphans(set()) == ["crash.bin"]
    assert write(store, "crash.bin", b"exact").sha256 == hashlib.sha256(b"exact").hexdigest()


def test_exact_bytes_headers_nulls_coordinates_and_timestamps_round_trip(store):
    records = [
        source(),
        source(1, b"", b""),
        source(2, None, b"key"),
        replace(source(3), broker_timestamp=datetime.now(UTC), partition=2),
    ]
    receipt = BronzeCapture(store).ingest_bronze(records)
    assert len(receipt.files) == 1 and receipt.files[0].row_count == 4
    assert read_bronze(store, receipt) == [replace(r, assignment_epoch="") for r in records]
    wrappers = [json.loads(line) for line in store.read(receipt.files[0].path).splitlines()]
    assert wrappers[0]["headers"] == [["x", None], ["x", ""]]
    assert wrappers[0]["key_base64"] is None and wrappers[1]["key_base64"] == ""
    assert wrappers[2]["value_base64"] is None
    assert all(r.source.raw_locator.endswith(f"#{i}") for i, r in enumerate(receipt.records, 1))
    assert receipt.captured_at >= max(r.bronze_durable_at for r in receipt.records)


def test_capture_is_not_a_final_disposition_or_commit_authorization(store):
    topic = "bench-m04.conversation-events.v1"
    worker = ConsumerGroup(
        "bench-m04.analytics.v1", [topic], "explicit-double", consumer_factory=ConsumerDouble
    )
    worker.consumer.messages.append(MessageDouble(topic, 0))
    records = worker.consume_records([topic], 1, 20)
    receipt = BronzeCapture(store).ingest_bronze(records)
    assert read_bronze(store, receipt)
    assert worker.durable_next_offsets() == {}
    assert not worker.commit_offsets({(topic, 0): 1}).succeeded
    worker.close()


def test_fixed_size_and_time_flushes_are_independent_of_sink_batching(store, monkeypatch):
    records = [source(i, b"x" * 60000) for i in range(20)]
    receipt = BronzeCapture(store).ingest_bronze(records)
    assert len(receipt.files) >= 2
    assert all(f.byte_size <= 1024 * 1024 for f in receipt.files)
    assert len(read_bronze(store, receipt)) == 20
    tick = iter([0.0, 0.010, 0.060, 0.060, 0.070, 0.070])
    monkeypatch.setattr(bronze, "monotonic", lambda: next(tick))
    timed = BronzeCapture(store).ingest_bronze([source(i) for i in range(3)])
    assert [f.row_count for f in timed.files] == [2, 1]


def test_capture_limits_and_raw_corruption_do_not_become_dirty_records(store):
    capture = BronzeCapture(store)
    with pytest.raises(CaptureTooLarge, match="wrapper"):
        capture.ingest_bronze([source(value=b"x" * 800000)])
    with pytest.raises(CaptureTooLarge, match="16-MiB"):
        capture.ingest_bronze([source(i, b"x" * 60000) for i in range(280)])
    with pytest.raises(ValueError, match="bounded"):
        capture.ingest_bronze([source()] * 2001)
    with pytest.raises(SourceCorruption):
        capture.ingest_bronze([replace(source(), raw_sha256="0" * 64)])
    with pytest.raises(ValueError, match="DLQ"):
        capture.ingest_bronze([replace(source(), topic="bench-m04.dead-letter.v1")])
    assert store.list_orphans(set()) == []


def test_receipt_hash_locator_and_membership_tampering_are_detected(store):
    receipt = BronzeCapture(store).ingest_bronze([source()])
    altered = receipt.model_copy(deep=True)
    altered.records[0].raw_sha256 = "0" * 64
    with pytest.raises(SourceCorruption):
        read_bronze(store, altered)
    altered = receipt.model_copy(deep=True)
    altered.records[0].source.raw_locator += "0"
    with pytest.raises(SourceCorruption):
        read_bronze(store, altered)
    altered = receipt.model_copy(deep=True)
    altered.records.append(altered.records[0])
    with pytest.raises(SourceCorruption):
        read_bronze(store, altered)
    path = store.root / receipt.files[0].path
    path.write_bytes(b"corruption")  # explicit external corruption fault
    with pytest.raises(SourceCorruption, match="hash"):
        read_bronze(store, receipt)


def test_restart_preserves_files_and_reports_unreferenced_capture_without_cleanup(store):
    receipt = BronzeCapture(store).ingest_bronze([source()])
    restarted = FileStore(store.root)
    assert read_bronze(restarted, receipt)[0].value_bytes == b"\xff{invalid"
    assert restarted.list_orphans(set()) == [receipt.files[0].path]
    assert restarted.list_orphans({f.path for f in receipt.files}) == []


def test_public_ingest_requires_explicit_volume_configuration(monkeypatch):
    monkeypatch.delenv("LAKEHOUSE_ROOT", raising=False)
    with pytest.raises(RuntimeError, match="LAKEHOUSE_ROOT"):
        bronze.ingest_bronze([source()])
