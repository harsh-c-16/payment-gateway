"""Apply only catalog_db migrations, checksum-verified. Caller owns the transaction."""

import hashlib
from pathlib import Path

MIGRATIONS = sorted((Path(__file__).resolve().parents[2] / "migrations/catalog").glob("*.sql"))


class MigrationChanged(RuntimeError):
    pass


def migrate_catalog(tx):
    with tx.transaction():
        tx.execute("SELECT pg_advisory_xact_lock(744032001)")
        tx.execute(
            "CREATE TABLE IF NOT EXISTS catalog_schema_migrations (version integer PRIMARY KEY, "
            "sha256 char(64) NOT NULL, applied_at timestamptz NOT NULL DEFAULT clock_timestamp())"
        )
        for version, path in enumerate(MIGRATIONS, 1):
            content = path.read_text(encoding="utf-8")
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            previous = tx.execute(
                "SELECT sha256 FROM catalog_schema_migrations WHERE version=%s", (version,)
            ).fetchone()
            if previous:
                if previous[0] != digest:
                    raise MigrationChanged(f"applied catalogue migration {version} changed")
                continue
            tx.execute(content)
            tx.execute(
                "INSERT INTO catalog_schema_migrations (version,sha256) VALUES (%s,%s)",
                (version, digest),
            )
