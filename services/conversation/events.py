"""Verified shared codec and caller-local outbox; never publish from M1."""

import os
from datetime import UTC, datetime
from threading import RLock
from uuid import uuid4

import psycopg
from pydantic import TypeAdapter

from shared.contracts.common import ErrorCode, Identifier, RequestContext

from .errors import ServiceError


def unavailable():
    return ServiceError(
        503,
        ErrorCode.DEPENDENCY_UNAVAILABLE,
        "Shared conversation event builder/outbox is unavailable.",
        details={"owners": ["Aditya", "Vichitr"]},
    )


class SharedEvents:
    mode = "real"

    def __init__(self, *, cache_path=None, dataset_revision=None):
        self.cache_path = cache_path
        self.dataset_revision = dataset_revision
        self._codec = None
        self._lock = RLock()

    def _bindings(self):
        try:
            from shared.event_transport import DEFAULT_CACHE, EventCodec
            from shared.event_transport.schemas import SchemaCache
            from shared.outbox import append_outbox

            if not callable(append_outbox):
                raise ImportError
            with self._lock:
                if self._codec is None:
                    revision = TypeAdapter(Identifier).validate_python(
                        self.dataset_revision or os.environ.get("CATALOG_DATASET_REVISION")
                    )
                    cache = SchemaCache.load(
                        self.cache_path or os.environ.get("EVENT_SCHEMA_CACHE_PATH", DEFAULT_CACHE)
                    )
                    self._codec = EventCodec(
                        cache, source_service="conversation", dataset_revision=revision
                    )
            return self._codec.build_event, append_outbox
        except Exception as exc:
            raise unavailable() from exc

    def check_revision(self, revision):
        self._bindings()
        if revision != self._codec.dataset_revision:
            raise unavailable()

    def event_codec(self):
        """Expose this producer's verified codec to its separate shared relay."""
        self._bindings()
        return self._codec

    def ready(self, database=None):
        self._bindings()
        if database is None:
            return
        # Exercise the actual builder and append under a rolled-back savepoint.
        # No readiness fact exists in the catalogue, so nothing may be committed.
        context = RequestContext(
            namespace="dev",
            run_id="m1-readiness",
            user_id="m1-readiness",
            correlation_id=str(uuid4()),
            request_id=str(uuid4()),
            session_id=str(uuid4()),
        )
        with database.transaction() as tx, tx.transaction():
            self.append(
                tx,
                event_type="CONVERSATION_TURN",
                payload={
                    "turn_id": str(uuid4()),
                    "mode": "fixed",
                    "outcome": "clarification",
                    "duration_ms": 0,
                    "llm_call_count": 0,
                    "extractor_source": "clarification",
                },
                context=context,
                version=1,
                event_time=datetime.now(UTC),
            )
            raise psycopg.Rollback()

    def quarantine(self, tx, diagnostic):
        try:
            from shared.event_transport import build_dlq_notice
            from shared.local_diagnostics import quarantine_local_diagnostic

            self._bindings()
            self._codec.encode(build_dlq_notice(diagnostic))
            return quarantine_local_diagnostic(tx, diagnostic)
        except psycopg.Error:
            raise
        except Exception as exc:
            raise unavailable() from exc

    def append(self, tx, *, event_type, payload, context, version, event_time):
        build_event, append_outbox = self._bindings()
        try:
            event = build_event(
                event_type=event_type,
                payload=payload,
                context=context,
                aggregate_type="session",
                aggregate_id=context.session_id,
                aggregate_version=version,
                event_time=event_time,
                metadata={
                    "synthetic": True,
                    "scenario_source": (
                        "benchmark" if context.namespace.startswith("bench-") else "simulation"
                    ),
                },
            )
            append_outbox(tx, event)
        except psycopg.Error:
            # Local database failures retain the storage error classification.
            raise
        except Exception as exc:
            raise unavailable() from exc
