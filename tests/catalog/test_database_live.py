"""Session reuse (the P1 variant) must not change transaction behaviour."""

import psycopg
import pytest

from services.catalog.database import Database
from services.catalog.errors import ServiceError


def test_reused_connections_keep_transaction_semantics(database_url, tmp_path, events):
    pooled = Database(database_url, max_connections=2, reuse_connections=True)
    with pooled.transaction() as tx:
        tx.execute("CREATE TABLE h_pool_check (value integer)")
    with pytest.raises(RuntimeError):
        with pooled.transaction() as tx:
            tx.execute("INSERT INTO h_pool_check VALUES (1)")
            raise RuntimeError("rolled back")
    with pooled.transaction() as tx:
        tx.execute("INSERT INTO h_pool_check VALUES (2)")
    with pooled.transaction() as tx:
        assert tx.execute("SELECT value FROM h_pool_check").fetchall() == [{"value": 2}]
    with pooled.transaction() as tx:
        first = tx.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]
    with pooled.transaction() as tx:
        assert tx.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"] == first


def test_reused_connection_that_died_is_replaced(database_url):
    pooled = Database(database_url, max_connections=1, reuse_connections=True)
    with pooled.transaction() as tx:
        pid = tx.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]
    with psycopg.connect(database_url, autocommit=True) as admin:
        admin.execute("SELECT pg_terminate_backend(%s)", (pid,))
    # The dead session is detected on use and discarded; the next caller gets a new one.
    with pytest.raises(ServiceError):
        with pooled.transaction() as tx:
            tx.execute("SELECT 1")
    with pooled.transaction() as tx:
        assert tx.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"] != pid


def test_o2_variant_adds_only_its_index(database_url):
    from pipelines.catalog.migrate import apply_variant

    with psycopg.connect(database_url, autocommit=True) as connection:
        count = "SELECT count(*) FROM pg_indexes WHERE schemaname=current_schema()"
        before = connection.execute(count).fetchone()[0]
        assert not connection.execute(
            "SELECT to_regclass('products_o2_category_price')"
        ).fetchone()[0]
        apply_variant(connection, "o2")
        apply_variant(connection, "o2")
        assert connection.execute(count).fetchone()[0] == before + 1
        assert connection.execute("SELECT to_regclass('products_o2_category_price')").fetchone()[0]
