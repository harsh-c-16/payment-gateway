"""Real PostgreSQL, isolated per-test schemas; missing DB is an explicit skip."""

import os
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from services.conversation.database import Database
from services.conversation.state import ConversationState
from shared.contracts.common import RequestContext

from .doubles import EventCaptureDouble


@pytest.fixture
def database():
    url = os.environ.get("P6_TEST_DATABASE_URL")
    if not url:
        pytest.skip("NOT_RUN: P6_TEST_DATABASE_URL required for real PostgreSQL 18 checks")
    schema = "p6_test_" + uuid4().hex
    with psycopg.connect(url, autocommit=True, connect_timeout=2) as admin:
        if not 180000 <= admin.info.server_version < 190000:
            pytest.fail("P6 real database checks require PostgreSQL 18")
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    database = Database(make_conninfo(url, options=f"-c search_path={schema}"))
    try:
        database.migrate()
        EventCaptureDouble.install(database)
        yield database
    finally:
        # Only the schema created above; never reset a namespace/database supplied by the user.
        assert schema.startswith("p6_test_") and len(schema) == 40
        with psycopg.connect(url, autocommit=True, connect_timeout=2) as admin:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.fixture
def state(database):
    return ConversationState(database, events=EventCaptureDouble())


@pytest.fixture
def context():
    return RequestContext(
        namespace="bench-p6-test",
        run_id=str(uuid4()),
        user_id="p6-synthetic-user",
        correlation_id=str(uuid4()),
        request_id=str(uuid4()),
        session_id=None,
    )
