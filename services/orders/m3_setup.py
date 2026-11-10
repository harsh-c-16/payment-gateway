"""Repeatable M3 schema setup for orders_db, inventory_db and payments_db.

One command applies each database's own migrations/<name>/*.sql under that database's
URL only, checksum-recorded in m3_schema_migrations (hashes use LF text, so Windows
CRLF checkouts match). Already-applied files are skipped; a changed applied file fails.
The SQL is idempotent, so a schema created earlier by hand is adopted on first run.

    python -m services.orders.m3_setup [orders] [inventory] [payments]

For projectctl's global `db migrate`, set
PROJECTCTL_OWNER_RUNTIME_MODULES=services.orders.m3_setup (exports runtime_bindings).
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[2]
DATABASES = {
    "orders": "ORDERS_DATABASE_URL",
    "inventory": "INVENTORY_DATABASE_URL",
    "payments": "PAYMENTS_DATABASE_URL",
}
# Distinct per database so concurrent setups of different databases never block each other.
LOCK_KEYS = {"orders": 744033001, "inventory": 744033002, "payments": 744033003}
REQUIRED_TABLES = {
    "orders": ("orders", "order_items", "saga_jobs", "operation_keys", "fault_barriers", "outbox"),
    "inventory": (
        "inventory",
        "inventory_seeds",
        "inventory_seed_chunks",
        "reservations",
        "reservation_items",
        "fault_barriers",
        "outbox",
    ),
    "payments": ("payment_orders", "payment_attempts", "ledger_entries", "outbox"),
}


class MigrationChanged(RuntimeError):
    pass


def migration_files(name):
    return sorted((ROOT / "migrations" / name).glob("*.sql"))


def migrate(connection, name):
    """Apply pending migrations for one M3 database in a single transaction."""
    applied = []
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_KEYS[name],))
        connection.execute(
            "CREATE TABLE IF NOT EXISTS m3_schema_migrations (version integer PRIMARY KEY, "
            "filename text NOT NULL, sha256 char(64) NOT NULL, "
            "applied_at timestamptz NOT NULL DEFAULT clock_timestamp())"
        )
        for version, path in enumerate(migration_files(name), 1):
            content = path.read_text(encoding="utf-8")
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            previous = connection.execute(
                "SELECT filename, sha256 FROM m3_schema_migrations WHERE version=%s", (version,)
            ).fetchone()
            if previous:
                if tuple(previous) != (path.name, digest):
                    raise MigrationChanged(
                        f"{name} migration {version} ({path.name}) differs from the applied file"
                    )
                continue
            connection.execute(content)
            connection.execute(
                "INSERT INTO m3_schema_migrations (version, filename, sha256) VALUES (%s,%s,%s)",
                (version, path.name, digest),
            )
            applied.append(path.name)
        missing = [
            table
            for table in REQUIRED_TABLES[name]
            if connection.execute("SELECT to_regclass(%s)", (table,)).fetchone()[0] is None
        ]
        if missing:
            raise MigrationChanged(f"{name} schema incomplete after migration: {missing}")
    return applied


def setup(name, url=None):
    url = url or os.environ.get(DATABASES[name], "")
    if not url:
        raise LookupError(f"{DATABASES[name]} is required")
    with psycopg.connect(url, connect_timeout=5) as connection:
        applied = migrate(connection, name)
    return {
        "database": name,
        "applied": applied,
        "verified": [path.name for path in migration_files(name)],
    }


def migration_participant(name):
    def participant(invocation):
        from projectctl.models import ExitCode
        from projectctl.providers import ProviderResult

        try:
            result = setup(name)
        except MigrationChanged as error:
            return ProviderResult(ExitCode.CORRECTNESS_FAILURE, (str(error),), "real")
        except LookupError as error:
            return ProviderResult(ExitCode.DEPENDENCY_FAILURE, (str(error),), "real")
        except (psycopg.Error, OSError) as error:
            return ProviderResult(
                ExitCode.DEPENDENCY_FAILURE,
                (f"{name} migration failed: {type(error).__name__}",),
                "real",
            )
        return ProviderResult(
            ExitCode.COMPLETED,
            (
                f"{name} migrations applied/verified; no other database changed",
                "applied: " + (", ".join(result["applied"]) or "none"),
            ),
            "real",
        )

    participant.__name__ = f"migrate_{name}"
    return participant


def runtime_bindings():
    from projectctl.runtime import RuntimeBindings

    return RuntimeBindings(migrations={name: migration_participant(name) for name in DATABASES})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "databases", nargs="*", metavar="database", help="orders, inventory, payments (default all)"
    )
    names = parser.parse_args(argv).databases or list(DATABASES)
    unknown = sorted(set(names) - DATABASES.keys())
    if unknown:
        parser.error(f"unknown database(s): {', '.join(unknown)}")
    status = 0
    for name in names:
        try:
            report = setup(name)
        except MigrationChanged as error:
            report, status = {"database": name, "error": str(error)}, 3
        except (LookupError, psycopg.Error, OSError) as error:
            report = {"database": name, "error": f"{type(error).__name__}: {error}"}
            status = max(status, 4)
        print(json.dumps(report))
    return status


if __name__ == "__main__":
    sys.exit(main())
