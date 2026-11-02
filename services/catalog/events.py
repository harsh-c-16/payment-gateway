"""The shared event builder plus Aditya's transactional append; missing bindings fail closed."""

import psycopg

from services.catalog.errors import ServiceError
from shared.contracts.common import ErrorCode


def unavailable():
    return ServiceError(
        503,
        ErrorCode.DEPENDENCY_UNAVAILABLE,
        "Shared catalogue event builder/outbox is unavailable.",
        details={"owners": ["Aditya", "Vichitr"]},
    )


class SharedEvents:
    mode = "real"

    def __init__(self):
        self.configured = False

    def _bindings(self):
        """Schemas are verified once here, so a service without its cache is never ready."""
        try:
            from shared.event_transport import build_event, configure_transport
            from shared.outbox import append_outbox

            if not self.configured:
                configure_transport(source_service="catalog")
                self.configured = True
        except Exception as error:
            raise unavailable() from error
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
            raise unavailable() from error
