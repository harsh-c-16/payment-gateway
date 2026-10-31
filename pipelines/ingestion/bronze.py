"""Bounded, exact-byte Bronze capture. Capture alone never permits Kafka commit."""

import base64
import hashlib
import json
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from time import monotonic
from uuid import uuid4

from pydantic import TypeAdapter

from pipelines.storage import FileStore
from shared.contracts.analytics import CapturedSource, FileDescriptor, RawBatchReceipt
from shared.contracts.common import UTCTime
from shared.contracts.events import Count, Namespace, SourceLocator, SourceRecord
from shared.event_transport.consumer import TOPIC, raw_fingerprint, record_size

CAPTURE_MAX_BYTES = 1024 * 1024
CAPTURE_MAX_SECONDS = 0.050
BATCH_MAX_RECORDS = 2000
BATCH_MAX_BYTES = 16 * 1024 * 1024


class CaptureTooLarge(RuntimeError):
    pass


class SourceCorruption(RuntimeError):
    pass


def validate_source(record):
    if not isinstance(record, SourceRecord):
        raise TypeError("Expected SourceRecord")
    TypeAdapter(Namespace).validate_python(record.source_namespace)
    if not isinstance(record.topic, str) or not TOPIC.fullmatch(record.topic):
        raise ValueError("Expected a namespaced business topic")
    if not record.topic.startswith(record.source_namespace + "."):
        raise ValueError("Source topic and namespace differ")
    if record.topic.endswith(".dead-letter.v1"):
        raise ValueError("DLQ notifications are not business Bronze ingestion")
    TypeAdapter(Count).validate_python(record.partition)
    TypeAdapter(Count).validate_python(record.offset)
    TypeAdapter(UTCTime).validate_python(record.ingested_at)
    if record.broker_timestamp is not None:
        TypeAdapter(UTCTime).validate_python(record.broker_timestamp)
    if not isinstance(record.headers, tuple):
        raise TypeError("Source headers must be an ordered tuple")
    for name, _ in record.headers:
        if not isinstance(name, str):
            raise TypeError("Header names must be text")
        name.encode("utf-8")
    for value in (record.key_bytes, record.value_bytes, *(v for _, v in record.headers)):
        if value is not None and not isinstance(value, bytes):
            raise TypeError("Source bytes must be bytes or null")
    if record.raw_sha256 != raw_fingerprint(record.key_bytes, record.value_bytes, record.headers):
        raise SourceCorruption("Source bytes do not match raw_sha256")


def _b64(value):
    return None if value is None else base64.b64encode(value).decode("ascii")


def _line(record, path, row):
    document = {
        "schema_version": 1,
        "namespace": record.source_namespace,
        "topic": record.topic,
        "partition": record.partition,
        "offset": record.offset,
        "key_base64": _b64(record.key_bytes),
        "value_base64": _b64(record.value_bytes),
        "headers": [[name, _b64(value)] for name, value in record.headers],
        "broker_timestamp": None
        if record.broker_timestamp is None
        else record.broker_timestamp.isoformat(),
        "ingested_at": record.ingested_at.isoformat(),
        "raw_sha256": record.raw_sha256,
        "raw_locator": f"{path}#{row}",
    }
    return (json.dumps(document, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


class BronzeCapture:
    def __init__(self, store):
        self.store = store

    def ingest_bronze(self, records):
        if not isinstance(records, Sequence) or not records or len(records) > BATCH_MAX_RECORDS:
            raise ValueError("Capture needs a nonempty bounded sequence of at most 2000 records")
        size = 0
        validate_source(records[0])
        namespace = records[0].source_namespace
        for record in records:
            validate_source(record)
            if record.source_namespace != namespace:
                raise ValueError("One capture uses one namespace")
            size += record_size(record)
            if size > BATCH_MAX_BYTES:
                raise CaptureTooLarge("Capture input exceeds the 16-MiB group bound")
        capture_id = str(uuid4())
        prefix = f"bronze/{namespace}/{capture_id}"
        files, captured, pending, lines = [], [], [], []
        byte_size = 0
        started = monotonic()

        def flush():
            nonlocal byte_size, started
            if not pending:
                return
            path = f"{prefix}-{len(files)}.jsonl"
            data = b"".join(lines)
            descriptor = self.store.write_immutable(path, data, hashlib.sha256(data).hexdigest())
            descriptor = FileDescriptor.model_validate(
                {
                    **descriptor.model_dump(),
                    "row_count": len(pending),
                    "schema_name": "bronze-wrapper",
                    "partition_values": {"namespace": namespace},
                }
            )
            durable_at = datetime.now(UTC)
            files.append(descriptor)
            for row, record in enumerate(pending, 1):
                captured.append(
                    CapturedSource(
                        namespace=namespace,
                        source=SourceLocator(
                            topic=record.topic,
                            partition=record.partition,
                            offset=record.offset,
                            raw_locator=f"{path}#{row}",
                        ),
                        raw_sha256=record.raw_sha256,
                        ingested_at=record.ingested_at,
                        bronze_durable_at=durable_at,
                    )
                )
            pending.clear()
            lines.clear()
            byte_size = 0
            started = monotonic()

        for record in records:
            if pending and monotonic() - started >= CAPTURE_MAX_SECONDS:
                flush()
            line = _line(record, f"{prefix}-{len(files)}.jsonl", len(pending) + 1)
            if len(line) > CAPTURE_MAX_BYTES:
                raise CaptureTooLarge("One encoded Bronze wrapper exceeds the 1-MiB file cap")
            if pending and byte_size + len(line) > CAPTURE_MAX_BYTES:
                flush()
                line = _line(record, f"{prefix}-{len(files)}.jsonl", 1)
            pending.append(record)
            lines.append(line)
            byte_size += len(line)
        flush()
        return RawBatchReceipt(
            capture_id=capture_id, files=files, records=captured, captured_at=datetime.now(UTC)
        )


def read_bronze(store, receipt):
    """Verify file hashes, exact membership/locators, and decoded source fingerprints."""
    receipt = RawBatchReceipt.model_validate(receipt)
    expected = {row.source.raw_locator: row for row in receipt.records}
    if len(expected) != len(receipt.records) or len({f.path for f in receipt.files}) != len(
        receipt.files
    ):
        raise SourceCorruption("Repeated Bronze locator or file")
    result = []
    for descriptor in receipt.files:
        data = store.read(descriptor.path)
        if (
            len(data) != descriptor.byte_size
            or hashlib.sha256(data).hexdigest() != descriptor.sha256
        ):
            raise SourceCorruption("Bronze file size/hash mismatch")
        lines = data.splitlines()
        if not data.endswith(b"\n") or len(lines) != descriptor.row_count:
            raise SourceCorruption("Bronze row count/framing mismatch")
        for row, line in enumerate(lines, 1):
            locator = f"{descriptor.path}#{row}"
            try:
                document = json.loads(line)
                if document["schema_version"] != 1 or document["raw_locator"] != locator:
                    raise ValueError("Unsupported/mismatched wrapper")
                record = SourceRecord(
                    document["namespace"],
                    document["topic"],
                    document["partition"],
                    document["offset"],
                    _decode(document["key_base64"]),
                    _decode(document["value_base64"]),
                    tuple((name, _decode(value)) for name, value in document["headers"]),
                    None
                    if document["broker_timestamp"] is None
                    else TypeAdapter(UTCTime).validate_python(document["broker_timestamp"]),
                    TypeAdapter(UTCTime).validate_python(document["ingested_at"]),
                    document["raw_sha256"],
                )
                validate_source(record)
                captured = expected.pop(locator)
                if (
                    captured.namespace != record.source_namespace
                    or captured.source.topic != record.topic
                    or captured.source.partition != record.partition
                    or captured.source.offset != record.offset
                    or captured.raw_sha256 != record.raw_sha256
                    or captured.ingested_at != record.ingested_at
                ):
                    raise ValueError("Receipt and wrapper differ")
            except (KeyError, TypeError, ValueError) as exc:
                raise SourceCorruption("Invalid Bronze wrapper/membership") from exc
            result.append(record)
    if expected:
        raise SourceCorruption("Receipt references missing Bronze rows")
    return result


def _decode(value):
    return None if value is None else base64.b64decode(value, validate=True)


def ingest_bronze(records):
    root = os.environ.get("LAKEHOUSE_ROOT")
    if not root:
        raise RuntimeError("LAKEHOUSE_ROOT must name the mounted durable data directory")
    return BronzeCapture(FileStore(root)).ingest_bronze(records)
