"""Shared synchronous SDK. Configure once at startup; no network work on import."""

import os
from pathlib import Path
from threading import RLock

from .codec import EventCodec, build_dlq_notice
from .consumer import ConsumerGroup
from .publisher import KafkaPublisher, RetryablePublishError
from .schemas import SchemaCache

__all__ = [
    "ConsumerGroup",
    "EventCodec",
    "KafkaPublisher",
    "RetryablePublishError",
    "build_dlq_notice",
    "build_event",
    "close_transport",
    "commit_offsets",
    "configure_transport",
    "consume_records",
    "validate_event",
    "publish_event",
]

_lock = RLock()
_codec = None
_publisher = None
_bootstrap = None
DEFAULT_CACHE = (
    Path(__file__).resolve().parents[2] / "artifacts/infra/streaming-local/registry-manifest.json"
)


def configure_transport(
    *, cache_path=None, bootstrap_servers=None, source_service=None, dataset_revision=None
):
    """Load all pinned schemas before readiness; use local cache even if registry is down."""
    global _codec, _bootstrap
    with _lock:
        if _publisher is not None:
            raise RuntimeError("close the existing publisher before reconfiguring")
        cache = SchemaCache.load(
            cache_path or os.environ.get("EVENT_SCHEMA_CACHE_PATH", DEFAULT_CACHE)
        )
        bootstrap = (
            os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:9092")
            if bootstrap_servers is None
            else bootstrap_servers
        )
        if not isinstance(bootstrap, str) or not bootstrap.strip():
            raise ValueError("Kafka bootstrap servers must be explicitly nonempty")
        _codec = EventCodec(
            cache,
            source_service=source_service,
            dataset_revision=(
                os.environ.get("CATALOG_DATASET_REVISION")
                if dataset_revision is None
                else dataset_revision
            ),
        )
        _bootstrap = bootstrap
        return _codec


def _get_codec():
    with _lock:
        if _codec is None:
            configure_transport()
        return _codec


def build_event(
    event_type,
    payload,
    context,
    aggregate_type,
    aggregate_id,
    aggregate_version,
    event_time,
    *,
    metadata=None,
    source_service=None,
):
    return _get_codec().build_event(
        event_type,
        payload,
        context,
        aggregate_type,
        aggregate_id,
        aggregate_version,
        event_time,
        metadata=metadata,
        source_service=source_service,
    )


def validate_event(raw_bytes, headers, topic, key, *, source_record=None, ingested_at=None):
    return _get_codec().validate_event(
        raw_bytes, headers, topic, key, source_record=source_record, ingested_at=ingested_at
    )


def publish_event(event, topic, key, *, timeout=15):
    global _publisher
    with _lock:
        codec = _get_codec()
        if _publisher is None:
            _publisher = KafkaPublisher(codec, _bootstrap)
        publisher = _publisher
    return publisher.publish_event(event, topic, key, timeout=timeout)


def consume_records(group, topics, max_records, max_wait_ms):
    return group.consume_records(topics, max_records, max_wait_ms)


def commit_offsets(group, durable_next_offsets):
    return group.commit_offsets(durable_next_offsets)


def close_transport():
    global _codec, _publisher
    with _lock:
        if _publisher is not None:
            _publisher.close()
        _publisher = None
        _codec = None
