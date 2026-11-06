"""Bounded connections to orders_db."""

from contextlib import contextmanager
from queue import Empty, LifoQueue
from threading import BoundedSemaphore

import psycopg
from psycopg.rows import dict_row

from services.orders.errors import storage_unavailable


class Database:
    def __init__(self, url, *, max_connections=10, reuse_connections=False):
        self.url = url
        self.slots = BoundedSemaphore(max_connections)
        self.idle = LifoQueue() if reuse_connections else None

    def _open(self):
        if self.idle is not None:
            try:
                return self.idle.get_nowait()
            except Empty:
                pass
        return psycopg.connect(self.url, connect_timeout=2, row_factory=dict_row)

    def _release(self, connection):
        if self.idle is not None and not connection.closed and not connection.broken:
            self.idle.put(connection)
        else:
            connection.close()

    @contextmanager
    def transaction(self, *, statement_timeout_ms=2000):
        if not self.url or not self.slots.acquire(timeout=2):
            raise storage_unavailable()
        connection = None
        try:
            connection = self._open()
            with connection.transaction():
                connection.execute(
                    "SELECT set_config('statement_timeout', %s, true)", (str(statement_timeout_ms),)
                )
                connection.execute("SET LOCAL lock_timeout = '2000ms'")
                connection.execute("SET LOCAL TIME ZONE 'UTC'")
                yield connection
        except psycopg.Error as error:
            if connection is not None:
                connection.close()
            raise storage_unavailable() from error
        finally:
            if connection is not None:
                self._release(connection)
            self.slots.release()
