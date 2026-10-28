"""Consume the shared builder and transactional append; never publish from M1.

The package entry points and caller-connection binding need owner review when
the shared implementations arrive. Missing handoffs fail closed, without a fake.
"""

import psycopg

from shared.contracts.common import ErrorCode

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

    def _bindings(self):
        try:
            from shared.event_transport import build_event
            from shared.outbox import append_outbox

            if not callable(build_event) or not callable(append_outbox):
                raise ImportError
            return build_event, append_outbox
        except ImportError as exc:
            raise unavailable() from exc

    def ready(self):
        self._bindings()

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
            )
            append_outbox(tx, event)
        except psycopg.Error:
            # Local database failures retain the storage error classification.
            raise
        except Exception as exc:
            raise unavailable() from exc
