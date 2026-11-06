"""Event building for inventory domain."""

import psycopg

from services.inventory.errors import ServiceError
from shared.contracts.common import ErrorCode


def _unavailable():
    return ServiceError(
        503,
        ErrorCode.DEPENDENCY_UNAVAILABLE,
        "Event transport is unavailable.",
    )


class InventoryEvents:
    def __init__(self):
        self.configured = False

    def _bindings(self):
        try:
            from shared.event_transport import build_event, configure_transport
            from shared.outbox import append_outbox

            if not self.configured:
                configure_transport(source_service="inventory")
                self.configured = True
        except Exception as error:
            raise _unavailable() from error
        return build_event, append_outbox

    def ready(self):
        self._bindings()

    def append(self, tx, **event):
        build_event, append_outbox = self._bindings()
        try:
            append_outbox(tx, build_event(**event))
        except psycopg.Error:
            raise
        except Exception as error:
            raise _unavailable() from error
