"""Catalogue owner bindings for the shared runner, on real PostgreSQL.

The SELECT-only audit roles are a deployment input, so reads here use the test schema's own
connection. Inventory gets its own schema, with its table and outbox shaped as Aditya's.
"""

import asyncio
import json
import os
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from pipelines.catalog import search_oracle
from pipelines.catalog.runtime import CatalogRuntime
from projectctl.models import ExitCode
from projectctl.providers import DependencyError, Invocation
from shared.contracts.common import RequestContext
from tests.catalog.helpers import import_rows, seed_stock
from tests.catalog.service_helpers import catalogue

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def inventory_url(database_url):
    base = os.environ["CATALOG_TEST_DATABASE_URL"]
    schema = "h_inv_" + uuid4().hex
    with psycopg.connect(base, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    url = make_conninfo(base, options=f"-c search_path={schema}")
    with psycopg.connect(url, autocommit=True) as tx:
        tx.execute((ROOT / "shared/outbox/schema.sql").read_text(encoding="utf-8"))
        tx.execute(
            "CREATE TABLE inventory (namespace varchar(62), sku varchar(64), on_hand bigint, "
            "reserved bigint, stock_version bigint, PRIMARY KEY (namespace, sku))"
        )
    yield url
    with psycopg.connect(base, autocommit=True) as admin:
        admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.fixture
def runtime(database_url, inventory_url, tmp_path):
    @contextmanager
    def read(variable):
        url = inventory_url if variable.startswith("INVENTORY") else database_url
        with psycopg.connect(url, autocommit=True) as tx:
            yield tx

    return CatalogRuntime(read=read, write_url=lambda: database_url)


@pytest.fixture
def stocked(tmp_path, database_url, db, events):
    """Every active SKU in stock, as at the frozen seed the search expectations assume."""
    namespace = "bench-h-" + uuid4().hex[:16]
    import_rows(tmp_path, database_url, namespace, catalogue())
    with psycopg.connect(database_url) as tx:
        active = [
            row[0]
            for row in tx.execute(
                "SELECT sku FROM products WHERE namespace=%s AND active ORDER BY sku", (namespace,)
            )
        ]
    seed_stock(db, events.codec, namespace, active)
    return namespace, active, tmp_path / namespace / "catalog.parquet"


def context(namespace, **extra):
    return {"namespace": namespace, "run_id": str(uuid4())} | extra


def outbox_row(url, namespace, published, run_id="seed-run"):
    with psycopg.connect(url, autocommit=True) as tx:
        tx.execute(
            "INSERT INTO outbox (event_id,namespace,aggregate_type,aggregate_id,topic,"
            "partition_key,payload,produced_at,published_at) VALUES "
            "(%s,%s,'stock','x','t','k',%s,now(),%s)",
            (
                uuid4(),
                namespace,
                json.dumps({"run_id": run_id}).encode(),
                datetime.now(UTC) if published else None,
            ),
        )


def test_fresh_proof_refuses_a_used_or_shared_namespace(runtime, stocked):
    namespace, _, _ = stocked
    fresh = "bench-h-" + uuid4().hex[:16]
    proof = asyncio.run(runtime.fresh_catalog_inventory(context(fresh)))
    assert proof["created_new"] is True and proof["namespace"] == fresh
    with pytest.raises(DependencyError, match="not fresh"):
        asyncio.run(runtime.fresh_catalog(context(namespace)))
    with pytest.raises(DependencyError, match="isolated bench"):
        asyncio.run(runtime.fresh_catalog(context("bench-prod-1")))


def test_seed_audit_combines_catalogue_and_inventory_and_checks_the_sku_set(
    runtime, stocked, inventory_url
):
    namespace, active, _ = stocked
    with psycopg.connect(inventory_url, autocommit=True) as tx:
        for sku in active:
            tx.execute("INSERT INTO inventory VALUES (%s,%s,10,0,1)", (namespace, sku))
    outbox_row(inventory_url, namespace, published=True)
    facts = asyncio.run(runtime.seed_audit(context(namespace)))
    assert facts["active_sku_count"] == facts["projected_sku_count"] == len(active)
    assert (facts["pending_outbox"], facts["run_id"], facts["deferred"]) == (0, "seed-run", 0)
    with psycopg.connect(inventory_url, autocommit=True) as tx:
        tx.execute("DELETE FROM inventory WHERE sku=%s", (active[0],))
    with pytest.raises(DependencyError, match="differing"):
        asyncio.run(runtime.seed_audit(context(namespace)))


def test_drain_waits_for_the_relay_and_fails_at_the_deadline(runtime, stocked, database_url):
    namespace, _, _ = stocked
    asyncio.run(runtime.drain(context(namespace), 5))
    outbox_row(database_url, namespace, published=False)
    with pytest.raises(DependencyError, match="1 unpublished"):
        asyncio.run(runtime.drain(context(namespace), 1))


def test_reset_deletes_only_its_namespace_after_a_clean_preflight(
    runtime, stocked, database_url, tmp_path
):
    namespace, _, _ = stocked
    other = "bench-h-" + uuid4().hex[:16]
    import_rows(tmp_path, database_url, other, catalogue())
    invocation = Invocation("env reset", {}, None, str(uuid4()), namespace)
    outbox_row(database_url, namespace, published=False)
    assert runtime.reset_preflight(invocation).code == ExitCode.DEPENDENCY_FAILURE
    with psycopg.connect(database_url, autocommit=True) as tx:
        tx.execute("UPDATE outbox SET published_at=now() WHERE namespace=%s", (namespace,))
    assert runtime.reset_preflight(invocation).code == ExitCode.COMPLETED
    result = runtime.reset_apply(invocation)
    assert result.code == ExitCode.COMPLETED, result.reasons
    with psycopg.connect(database_url) as tx:
        from pipelines.catalog.runtime import namespace_rows

        assert not any(namespace_rows(tx, namespace).values())
        assert namespace_rows(tx, other)["products"] > 0


def search_emissions(client, namespace, directory, tamper=None):
    queries = json.loads(search_oracle.QUERIES.read_text(encoding="utf-8"))["queries"]
    with (directory / "emissions.jsonl").open("w", encoding="utf-8") as stream:
        for repeat in range(2):
            for query in queries:
                principal = RequestContext(
                    namespace=namespace,
                    run_id=str(uuid4()),
                    user_id="buyer",
                    correlation_id=str(uuid4()),
                    request_id=str(uuid4()),
                    session_id=str(uuid4()),
                )
                body = query["request"] | {
                    "request_id": principal.request_id,
                    "session_id": principal.session_id,
                }
                response = client.post(
                    "/v1/search", json=body, headers=principal.headers(str(uuid4()))
                )
                row = {"payload": {"query_id": query["query_id"]}}
                if response.status_code == 200:
                    body = response.json()
                    if tamper and repeat == 1:
                        tamper(query, body)
                    row |= {"outcome": "acknowledged", "details": {"search": body}}
                else:
                    row |= {"outcome": "failed", "details": None}
                stream.write(json.dumps(row) + "\n")


@pytest.fixture
def search_world(stocked, db, events, tmp_path, monkeypatch, runtime):
    from starlette.testclient import TestClient

    from services.catalog.app import create_app

    namespace, _, catalog = stocked
    expectations = tmp_path / "search_expectations.json"
    expectations.write_text(json.dumps(search_oracle.expectations(catalog)))
    monkeypatch.setattr("pipelines.catalog.runtime.SEARCH_EXPECTATIONS", expectations)
    monkeypatch.delenv("CATALOG_BINDING_REVIEW_PATH", raising=False)
    client = TestClient(create_app(db=db, events=events), raise_server_exceptions=False)
    return client, namespace


def test_search_audit_matches_the_independent_oracle_and_writes_raw_evidence(
    search_world, runtime, tmp_path
):
    client, namespace = search_world
    run = tmp_path / "run"
    run.mkdir()
    search_emissions(client, namespace, run)
    verdict = asyncio.run(runtime.search_audit(context(namespace), run))
    assert verdict["passed"] is True, verdict["mismatched_paths"]
    for name in ("expected.json", "observed.json", "query_results.parquet", "source_fixture.json"):
        assert (run / name).stat().st_size
    observed = json.loads((run / "observed.json").read_text())
    assert observed["collection_complete"] is True and observed["test_mode"] == "real"


def test_search_audit_fails_on_a_filter_violation_or_a_changed_count(
    search_world, runtime, tmp_path
):
    client, namespace = search_world

    def tamper(query, body):
        if query["query_id"] == "B01":
            body["eligible_count"] += 1
            body["candidate_count"] += 1
        if body["hits"] and query["request"]["intent"]["category"] == "clothing":
            body["hits"][0]["sku"] = "FK-WATCH1"

    run = tmp_path / "run"
    run.mkdir()
    search_emissions(client, namespace, run, tamper)
    verdict = asyncio.run(runtime.search_audit(context(namespace), run))
    assert verdict["passed"] is False
    assert "/B01/eligible_count" in verdict["mismatched_paths"]
    assert any(path.endswith("/hard_filter_violations") for path in verdict["mismatched_paths"])


def test_team_runtime_composes_catalogue_hooks_beside_m4(monkeypatch):
    from projectctl.team_runtime import runtime_bindings

    monkeypatch.setenv("PROJECTCTL_OWNER_RUNTIME_MODULES", "pipelines.catalog.runtime")
    monkeypatch.delenv("ANALYTICS_FROZEN_LAYOUTS", raising=False)
    runtime = runtime_bindings()
    assert {"W-PIPE", "W-IMPORT", "W-SEARCH", "W-ANALYTICS"} <= set(runtime.workloads)
    assert "catalog" in runtime.resets
    search = runtime.workloads["W-SEARCH"]
    assert all(
        getattr(search, name) is not None
        for name in ("fresh_namespace", "seed_audit", "drain", "audit", "observer_factory")
    )
    # Without a frozen layout file the runner keeps W-ANALYTICS visibly blocked.
    assert runtime.workloads["W-ANALYTICS"].layout_for is None
