"""Explicit event-builder/outbox/turn doubles, never imported by production code.

The SQL capture table belongs only to tests. It is NOT Aditya's outbox schema,
relay, Kafka path, schema validation, or proof of the shared event integration.
"""

from datetime import UTC, datetime
from uuid import uuid4

from psycopg.types.json import Jsonb

from services.conversation.events import unavailable
from shared.contracts.conversation import TurnResponse, TurnTimings


class EventCaptureDouble:
    mode = "stub"

    def __init__(self, *, fail_after_append=False):
        self.fail_after_append = fail_after_append

    @staticmethod
    def install(database):
        with database.transaction(statement_timeout_ms=60000) as tx:
            tx.execute(
                "CREATE TABLE IF NOT EXISTS p6_test_event_capture "
                "(event_id uuid PRIMARY KEY, namespace text NOT NULL, session_id uuid NOT NULL, "
                "aggregate_version bigint NOT NULL, event_type text NOT NULL, "
                "event jsonb NOT NULL, UNIQUE(namespace,session_id,aggregate_version))"
            )

    def ready(self):
        pass

    def append(self, tx, *, event_type, payload, context, version, event_time):
        assert event_type in {"ADD_TO_CART", "CONVERSATION_TURN"}
        assert "text" not in payload and "response_text" not in payload
        event = {
            "event_id": str(uuid4()),
            "event_type": event_type,
            "source_service": "conversation",
            "schema_version": 1,
            "namespace": context.namespace,
            "run_id": context.run_id,
            "user_id": context.user_id,
            "session_id": context.session_id,
            "correlation_id": context.correlation_id,
            "aggregate_type": "session",
            "aggregate_id": context.session_id,
            "aggregate_version": version,
            "event_time": event_time.isoformat(),
            "produced_at": datetime.now(UTC).isoformat(),
            "payload": payload,
            "metadata": {"test_double": True},
        }
        tx.execute(
            "INSERT INTO p6_test_event_capture "
            "(event_id,namespace,session_id,aggregate_version,event_type,event) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (
                event["event_id"],
                context.namespace,
                context.session_id,
                version,
                event_type,
                Jsonb(event),
            ),
        )
        if self.fail_after_append:
            raise unavailable()


class TurnOutcomeDouble:
    """No parser, provider, model or workflow; deterministic persistence input only."""

    def __init__(self):
        self.calls = 0

    def __call__(self, request, context):
        self.calls += 1
        return TurnResponse(
            turn_id=str(uuid4()),
            response_text="Explicit P6 storage-test outcome.",
            intent=None,
            search_id=None,
            products=[],
            proposed_action=None,
            outcome="clarification",
            extractor_source="clarification",
            llm_call_count=0,
            timings_ms=TurnTimings(parse=0, llm=None, search=0, compose=0, total=0),
        )
