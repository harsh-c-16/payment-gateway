"""Real analytics PostgreSQL and FileStore; Vichitr's real publisher, no broker."""

import os
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from analytics.queries.fixture import offline_cache
from pipelines.curation import AnalyticsPipeline
from pipelines.ingestion.receipts import migrate_analytics
from pipelines.storage import FileStore
from shared.event_transport.codec import EventCodec


@pytest.fixture
def pipeline(tmp_path):
    url = os.environ.get("ANALYTICS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("NOT_RUN: ANALYTICS_TEST_DATABASE_URL required for real PostgreSQL 18 checks")
    schema = "h_an_" + uuid4().hex
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    scoped = make_conninfo(url, options=f"-c search_path={schema} -c timezone=UTC")

    def connect():
        return psycopg.connect(scoped, autocommit=True)

    with connect() as tx, tx.transaction():
        migrate_analytics(tx)
    root = tmp_path / "lake"
    root.mkdir()
    built = AnalyticsPipeline(
        connect,
        FileStore(root),
        EventCodec(offline_cache(), source_service="catalog"),
        code_commit="test",
    )
    built.test_root = root
    built.test_namespace = "bench-h-an-" + uuid4().hex[:12]
    try:
        yield built
    finally:
        assert schema.startswith("h_an_")
        with psycopg.connect(url, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
