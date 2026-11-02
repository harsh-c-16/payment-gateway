"""Bounded connections to catalog_db; common Appendix A caps a service at ten."""

from contextlib import contextmanager
from threading import BoundedSemaphore

import psycopg
from psycopg.rows import dict_row

from services.catalog.errors import storage_unavailable


class Database:
    def __init__(self, url, *, max_connections=10):
        self.url = url
        self.slots = BoundedSemaphore(max_connections)

    @contextmanager
    def transaction(self, *, statement_timeout_ms=2000):
        """Yields a dict-row connection; commits on clean exit, rolls back on an exception."""
        if not self.url or not self.slots.acquire(timeout=2):
            raise storage_unavailable()
        try:
            with psycopg.connect(self.url, connect_timeout=2, row_factory=dict_row) as tx:
                tx.execute(
                    "SELECT set_config('statement_timeout', %s, true)", (str(statement_timeout_ms),)
                )
                tx.execute("SET LOCAL lock_timeout = '2000ms'")
                tx.execute("SET LOCAL TIME ZONE 'UTC'")
                yield tx
        except psycopg.Error as error:
            raise storage_unavailable() from error
        finally:
            self.slots.release()
