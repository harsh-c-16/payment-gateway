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
from psycopg.types.json import Jsonb

from pipelines.catalog.migrate import migrate_catalog
from shared.contracts.common import RequestContext
from shared.event_transport.codec import EventCodec
from tests.pipelines.transport_doubles import offline_cache

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


class EventCaptureDouble:
    """Test double, not Aditya's outbox. Events are schema-validated, then stored in the caller's
    transaction so a rollback also removes them. Nothing is published."""

    mode = "stub"

    def __init__(self):
        self.codec = EventCodec(offline_cache(), source_service="catalog")

    def ready(self):
        pass

    def append(self, tx, **event):
        built = self.codec.build_event(**event)
        tx.execute(
            "INSERT INTO test_event_capture (event) VALUES (%s)",
            (Jsonb(built.model_dump(mode="json")),),
        )


@pytest.fixture
def events():
    return EventCaptureDouble()


@pytest.fixture
def outbox_double(monkeypatch):
    """Lets the real diagnostics helper run in tests; proves nothing about the real relay."""
    appended = []
    module = ModuleType("shared.outbox")
    module.append_outbox = lambda tx, event: appended.append(event)
    monkeypatch.setitem(sys.modules, "shared.outbox", module)
    return appended


def make_context(namespace=None, user="h-synthetic-user", session=None):
    return RequestContext(
        namespace=namespace or "bench-h-" + uuid4().hex[:20],
        run_id=str(uuid4()),
        user_id=user,
        correlation_id=str(uuid4()),
        request_id=str(uuid4()),
        session_id=session,
    )


@pytest.fixture
def context():
    return make_context()


@pytest.fixture
def source_csv():
    if not SOURCE.is_file():
        pytest.skip("NOT_RUN: data/raw/flipkart_com-ecommerce_sample.csv not present")
    return SOURCE


@pytest.fixture
def world(tmp_path, database_url, db, events, monkeypatch, outbox_double):
    """A small promoted catalogue with projected stock behind the real HTTP app."""
    from starlette.testclient import TestClient

    from services.catalog.app import create_app
    from tests.catalog.helpers import import_rows, seed_stock
    from tests.catalog.service_helpers import TOKEN, catalogue

    monkeypatch.setenv("INTERNAL_API_TOKEN", TOKEN)
    namespace = "bench-h-" + uuid4().hex[:16]
    report, _ = import_rows(tmp_path, database_url, namespace, catalogue())
    seed_stock(
        db,
        events.codec,
        namespace,
        ["FK-SHIRT1", "FK-SHIRT2", "FK-SHIRT3", "FK-DRESS1", "FK-WATCH1", "FK-ODD1"],
    )
    seed_stock(db, events.codec, namespace, ["FK-ZEROSTOCK"], on_hand=0, start_offset=2000)
    client = TestClient(create_app(db=db, events=events), raise_server_exceptions=False)
    return client, namespace, report


@pytest.fixture(scope="session")
def encoder():
    """The real locked model when present; the semantic tests skip visibly otherwise."""
    pytest.importorskip("onnxruntime")
    directory = Path(__file__).resolve().parents[2] / "artifacts/models/all-MiniLM-L6-v2"
    if not (directory / "model.onnx").is_file():
        pytest.skip("NOT_RUN: locked embedding model files not present")
    from services.catalog.embedding import Encoder

    return Encoder(directory)
