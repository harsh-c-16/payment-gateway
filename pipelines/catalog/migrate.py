"""Apply only catalog_db migrations, checksum-verified. Caller owns the transaction."""

import argparse
import hashlib
import os
from pathlib import Path

import psycopg

MIGRATIONS = sorted((Path(__file__).resolve().parents[2] / "migrations/catalog").glob("*.sql"))
VARIANTS = {
    "prototype": MIGRATIONS[0].parent / "variants/prototype_eligible.sql",
    "o2": MIGRATIONS[0].parent / "variants/o2_category_price_btree.sql",
    "r-ann": MIGRATIONS[0].parent / "variants/r_ann_hnsw.sql",
}


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


def apply_variant(connection, name):
    """Optional index experiments stay out of the base migrations, so B0 never carries them."""
    connection.execute(VARIANTS[name].read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description="Apply catalogue migrations and optional variants")
    parser.add_argument("--variant", choices=sorted(VARIANTS))
    arguments = parser.parse_args()
    with psycopg.connect(os.environ["CATALOG_DATABASE_URL"], autocommit=True) as connection:
        with connection.transaction():
            migrate_catalog(connection)
        if arguments.variant:
            apply_variant(connection, arguments.variant)


if __name__ == "__main__":
    main()
