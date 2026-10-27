"""Bounded PostgreSQL 18 connections and checksum-verified M1 migrations."""

import argparse
import hashlib
import os
from contextlib import contextmanager
from pathlib import Path
from threading import BoundedSemaphore

import psycopg
from psycopg.rows import dict_row

from shared.contracts.common import ErrorCode

from .errors import ServiceError

MIGRATION = Path(__file__).resolve().parents[2] / "migrations/conversation/001_state.sql"


def migration_content():
    # Normalize checkout line endings before comparing across Windows/Linux.
    return MIGRATION.read_text(encoding="utf-8").encode("utf-8")


def storage_unavailable():
    return ServiceError(503, ErrorCode.STORAGE_UNAVAILABLE, "Conversation storage is unavailable.")


class Database:
    def __init__(self, url: str):
        self.url = url
        self.slots = BoundedSemaphore(10)

    @contextmanager
    def transaction(self, *, statement_timeout_ms=2000):
        if not self.url:
            raise storage_unavailable()
        if not self.slots.acquire(timeout=2):
            raise storage_unavailable()
        try:
            with psycopg.connect(self.url, connect_timeout=2, row_factory=dict_row) as tx:
                tx.execute(
                    "SELECT set_config('statement_timeout', %s, true)", (str(statement_timeout_ms),)
                )
                tx.execute("SET LOCAL lock_timeout = '2000ms'")
                tx.execute("SET LOCAL TIME ZONE 'UTC'")
                yield tx
        except psycopg.Error as exc:
            raise storage_unavailable() from exc
        finally:
            self.slots.release()

    def _version(self, tx):
        version = int(tx.execute("SHOW server_version_num").fetchone()["server_version_num"])
        if not 180000 <= version < 190000:
            raise storage_unavailable()

    def migrate(self):
        content = migration_content()
        digest = hashlib.sha256(content).hexdigest()
        # DDL is setup work, not an API command; retain the 2-second lock bound.
        with self.transaction(statement_timeout_ms=60000) as tx:
            self._version(tx)
            tx.execute("SELECT pg_advisory_xact_lock(18006001)")
            tx.execute(
                "CREATE TABLE IF NOT EXISTS conversation_schema_migrations "
                "(version integer PRIMARY KEY, sha256 char(64) NOT NULL, "
                "applied_at timestamptz NOT NULL DEFAULT clock_timestamp())"
            )
            previous = tx.execute(
                "SELECT sha256 FROM conversation_schema_migrations WHERE version = 1"
            ).fetchone()
            if previous:
                if previous["sha256"] != digest:
                    raise storage_unavailable()
                return
            tx.execute(content.decode("utf-8"))
            tx.execute(
                "INSERT INTO conversation_schema_migrations (version, sha256) VALUES (1, %s)",
                (digest,),
            )

    def ready(self):
        with self.transaction() as tx:
            self._version(tx)
            row = tx.execute(
                "SELECT sha256 FROM conversation_schema_migrations WHERE version = 1"
            ).fetchone()
            if not row or row["sha256"] != hashlib.sha256(migration_content()).hexdigest():
                raise storage_unavailable()
            tx.execute("SELECT 1 FROM sessions, carts, cart_items, turns, operation_keys LIMIT 0")


def main():
    argparse.ArgumentParser(description="Apply only conversation-owned migrations.").parse_args()
    url = os.environ.get("CONVERSATION_DATABASE_URL")
    if not url:
        print("CONVERSATION_DATABASE_URL is required; no default database is selected.")
        return 4
    try:
        Database(url).migrate()
    except ServiceError:
        print("M1 migration failed: STORAGE_UNAVAILABLE (connection details withheld).")
        return 4
    print(
        "M1 state migration 1 applied/verified; "
        "shared outbox/diagnostic DDL remains owner-supplied."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
