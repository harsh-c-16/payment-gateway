"""Real PostgreSQL in an isolated per-test schema; a missing database is a visible skip."""

import os
import sys
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from pipelines.catalog.migrate import migrate_catalog

SOURCE = Path(__file__).resolve().parents[2] / "data/raw/flipkart_com-ecommerce_sample.csv"


@pytest.fixture
def database_url(monkeypatch, tmp_path):
    url = os.environ.get("CATALOG_TEST_DATABASE_URL")
    if not url:
        pytest.skip("NOT_RUN: CATALOG_TEST_DATABASE_URL required for real PostgreSQL 18 checks")
    schema = "h_test_" + uuid4().hex
    monkeypatch.setenv("LAKEHOUSE_ROOT", str(tmp_path / "lake"))
    with psycopg.connect(url, autocommit=True, connect_timeout=5) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    scoped = make_conninfo(url, options=f"-c search_path={schema},public")
    with psycopg.connect(scoped, connect_timeout=5) as tx:
        migrate_catalog(tx)
        tx.execute(
            "CREATE TABLE test_event_capture (position bigint GENERATED ALWAYS AS IDENTITY, "
            "event jsonb NOT NULL)"
        )
    try:
        yield scoped
    finally:
        assert schema.startswith("h_test_") and len(schema) == 39
        with psycopg.connect(url, autocommit=True, connect_timeout=5) as admin:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.fixture
def db(database_url):
    from services.catalog.database import Database

    return Database(database_url)


@pytest.fixture
def outbox_double(monkeypatch):
    """Lets the real diagnostics helper run in tests; proves nothing about the real relay."""
    appended = []
    module = ModuleType("shared.outbox")
    module.append_outbox = lambda tx, event: appended.append(event)
    monkeypatch.setitem(sys.modules, "shared.outbox", module)
    return appended


@pytest.fixture
def source_csv():
    if not SOURCE.is_file():
        pytest.skip("NOT_RUN: data/raw/flipkart_com-ecommerce_sample.csv not present")
    return SOURCE
