"""Opt-in real Docker check; never substitute a native DB or a test double."""

import json
import os
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from infra import postgres, streaming
from projectctl.models import ExitCode
from projectctl.providers import Invocation


@pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_LIVE_TESTS") != "1",
    reason="Real Docker required; opt in with RUN_POSTGRES_LIVE_TESTS=1",
)
def test_real_isolation_and_persistence_across_container_recreation():
    result = streaming.adapter(
        Invocation("env up", {"profile": "streaming-local"}, None, str(uuid4()), "bench-m01")
    )
    assert result.code == ExitCode.COMPLETED, result.reasons
    values = postgres.credentials()
    allocation = json.loads((postgres.ROOT / "infra/streaming-profile.json").read_text())[
        "services"
    ]["postgres"]
    before = postgres.verify(**allocation)
    before_container = streaming.compose("ps", "--quiet", "postgres")
    denials = []
    for service in postgres.SERVICES:
        for other in postgres.SERVICES:
            if service == other:
                continue
            url = postgres.database_url(service, values).rsplit("/", 1)[0] + f"/{other}_db"
            with pytest.raises(psycopg.OperationalError) as failure:
                psycopg.connect(url, connect_timeout=3)
            # libpq connection failures do not carry a PGresult/SQLSTATE.
            assert f'permission denied for database "{other}_db"' in str(failure.value)
            denials.append({"login": service, "database": other, "outcome": "permission_denied"})
    table = sql.Identifier("m01_probe_" + uuid4().hex)
    marker = str(uuid4())
    url = postgres.database_url("analytics", values)
    with psycopg.connect(url) as tx:
        tx.execute(sql.SQL("CREATE TABLE {} (value text NOT NULL)").format(table))
        tx.execute(sql.SQL("INSERT INTO {} VALUES (%s)").format(table), (marker,))
    # Only this Compose project's container is recreated; its named volume is retained.
    streaming.compose("stop", "--timeout", "30", "postgres")
    streaming.compose("rm", "--force", "postgres")
    streaming.compose("up", "--detach", "--wait", "--wait-timeout", "90", "postgres")
    after = postgres.verify(**allocation)
    after_container = streaming.compose("ps", "--quiet", "postgres")
    assert before["data_volume"] == after["data_volume"]
    assert before_container != after_container
    with psycopg.connect(url) as tx:
        assert tx.execute(sql.SQL("SELECT value FROM {}").format(table)).fetchall() == [(marker,)]
        tx.execute(sql.SQL("DROP TABLE {}").format(table))
    out = postgres.RUNTIME / "checks" / str(uuid4())
    out.mkdir(parents=True, exist_ok=False)
    with (out / "live-test.json").open("x", encoding="utf-8") as stream:
        json.dump(
            {
                "before": before,
                "after": after,
                "before_container": before_container,
                "after_container": after_container,
                "cross_database_denials": denials,
                "persisted_marker_matched": True,
                "probe_removed": True,
                "verified_resource_allocation": allocation,
            },
            stream,
            indent=2,
        )
