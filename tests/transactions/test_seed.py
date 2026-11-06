"""Seed validation and real SQL/outbox atomicity; schema cache is an explicit offline fixture."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

import services.inventory.adapter as adapter
import services.inventory.seed as seeding
import shared.event_transport as sdk
from projectctl.models import ExitCode
from projectctl.providers import Invocation
from services.inventory.database import Database
from services.inventory.errors import storage_unavailable
from services.inventory.events import InventoryEvents
from shared.contracts.common import RequestContext
from shared.event_transport.codec import EventCodec
from shared.event_transport.schemas import canonical_json
from tests.pipelines.transport_doubles import offline_cache

ROOT = Path(__file__).resolve().parents[2]


def manifest(namespace, count=3):
    result = json.loads((ROOT / "contracts/fixtures/catalog/sku_manifest.example.json").read_text())
    result["namespace"] = namespace
    result["sorted_skus"] = [
        {
            "sku": f"FK-{i:05}",
            "product_id": f"FK-{i:05}",
            "source_pid": str(i),
            "source_observation_id": f"obs-{i}",
        }
        for i in range(count)
    ]
    result["sku_count"] = count
    rehash(result)
    return result


def rehash(document):
    content = {key: value for key, value in document.items() if key != "content_sha256"}
    document["content_sha256"] = hashlib.sha256(canonical_json(content)).hexdigest()


@pytest.fixture
def context():
    return RequestContext(
        namespace="bench-seed-" + uuid4().hex[:12],
        run_id="seed-test",
        user_id="seed-test",
        correlation_id=str(uuid4()),
        request_id=str(uuid4()),
        session_id=None,
    )


@pytest.mark.parametrize("bad", ["hash", "count", "duplicate", "order", "namespace", "revision"])
def test_invalid_manifest_is_rejected_before_database_access(context, bad):
    document = manifest(context.namespace)
    if bad == "hash":
        document["content_sha256"] = "f" * 64
    elif bad == "count":
        document["sku_count"] += 1
    elif bad == "duplicate":
        document["sorted_skus"][1] = document["sorted_skus"][0]
    elif bad == "order":
        document["sorted_skus"].reverse()
    elif bad == "namespace":
        document["namespace"] = "bench-other"
    else:
        document["dataset_revision"] = ""
    if bad != "hash":
        rehash(document)
    with pytest.raises(ValueError):
        seeding.seed_inventory(None, context.namespace, document, events=None, context=context)


def test_adapter_matches_cli_manifest_and_function(tmp_path, monkeypatch, context):
    document = manifest(context.namespace)
    path = tmp_path / "skus.json"
    path.write_text(json.dumps(document))
    monkeypatch.setenv("INVENTORY_DATABASE_URL", "explicit-unused-test-url")
    calls = []

    def capture(db, namespace, manifest, *, events, context, seed, default_on_hand):
        calls.append((namespace, manifest, seed, default_on_hand, context.run_id))
        return {"seeded_count": 3}

    monkeypatch.setattr(adapter, "seed_inventory", capture)
    invocation = Invocation(
        "inventory seed",
        {"sku_manifest": path, "profile": "performance", "seed": 123},
        None,
        "non-uuid-run",
        context.namespace,
    )
    assert adapter.inventory_seed(invocation).code == ExitCode.COMPLETED
    assert calls == [(context.namespace, document, 123, 10_000, "non-uuid-run")]
    monkeypatch.delenv("INVENTORY_DATABASE_URL")
    assert adapter.inventory_seed(invocation).code == ExitCode.DEPENDENCY_FAILURE
    path.write_text("{")
    assert adapter.inventory_seed(invocation).code == ExitCode.BAD_INPUT


@pytest.fixture
def database(monkeypatch):
    import os

    url = os.environ.get("INVENTORY_TEST_DATABASE_URL")
    if not url:
        pytest.skip("NOT_RUN: INVENTORY_TEST_DATABASE_URL required for real PostgreSQL 18 checks")
    schema = "m3_seed_" + uuid4().hex
    with psycopg.connect(url, autocommit=True) as tx:
        assert 180000 <= tx.info.server_version < 190000
        tx.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    scoped = make_conninfo(url, options=f"-c search_path={schema}")
    try:
        with psycopg.connect(scoped) as tx:
            for path in sorted((ROOT / "migrations/inventory").glob("*.sql")):
                tx.execute(path.read_text())
        monkeypatch.setenv("INVENTORY_DATABASE_URL", scoped)
        yield Database(scoped)
    finally:
        assert schema.startswith("m3_seed_") and len(schema) == 40
        with psycopg.connect(url, autocommit=True) as tx:
            tx.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.fixture
def events(monkeypatch):
    monkeypatch.setattr(sdk, "_codec", EventCodec(offline_cache(), source_service="inventory"))
    built = InventoryEvents()
    built.configured = True
    return built


def counts(database):
    with database.transaction() as tx:
        return tuple(
            tx.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]
            for table in ("inventory", "outbox", "inventory_seed_chunks")
        )


def test_seed_uses_real_outbox_and_never_refills(database, events, context):
    document = manifest(context.namespace)
    first = seeding.seed_inventory(
        database, context.namespace, document, events=events, context=context
    )
    assert first["seeded_count"] == 3 and counts(database) == (3, 3, 1)
    with database.transaction() as tx:
        rows = tx.execute("SELECT payload FROM outbox ORDER BY outbox_id").fetchall()
        for row in rows:
            event = json.loads(bytes(row["payload"]))
            assert event["event_type"] == "STOCK_UPDATED"
            assert event["payload"]["on_hand"] == 10_000
            assert event["metadata"]["dataset_revision"] == document["dataset_revision"]
            assert event["metadata"]["synthetic"] is True
        tx.execute("UPDATE inventory SET on_hand=9999, stock_version=2")
    second = seeding.seed_inventory(
        database, context.namespace, document, events=events, context=context
    )
    assert second["seed_id"] == first["seed_id"] and second["seeded_count"] == 0
    assert second["initial_stock_digest"] == first["initial_stock_digest"]
    assert counts(database) == (3, 3, 1)
    with database.transaction() as tx:
        assert tx.execute("SELECT min(on_hand) AS n FROM inventory").fetchone()["n"] == 9999
        assert tx.execute("SELECT status FROM inventory_seeds").fetchone()["status"] == "COMPLETE"
    with pytest.raises(ValueError, match="fresh namespace"):
        seeding.seed_inventory(
            database, context.namespace, document, events=events, context=context, seed=43
        )


def test_failed_chunk_rolls_back_then_resumes(database, events, context, monkeypatch):
    monkeypatch.setattr(seeding, "CHUNK_ROWS", 2)
    document = manifest(context.namespace, 4)
    append = events.append
    calls = []

    def fail(tx, **event):
        append(tx, **event)
        calls.append(event)
        if len(calls) == 3:
            raise RuntimeError("explicit failure after outbox insertion")

    monkeypatch.setattr(events, "append", fail)
    with pytest.raises(RuntimeError, match="explicit failure"):
        seeding.seed_inventory(
            database, context.namespace, document, events=events, context=context
        )
    assert counts(database) == (2, 2, 1)
    monkeypatch.setattr(events, "append", append)
    report = seeding.seed_inventory(
        database, context.namespace, document, events=events, context=context
    )
    assert report["seeded_count"] == 2 and counts(database) == (4, 4, 2)


def test_concurrent_same_seed_creates_one_effect(database, events, context, monkeypatch):
    monkeypatch.setattr(seeding, "CHUNK_ROWS", 2)
    document = manifest(context.namespace, 5)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                seeding.seed_inventory,
                database,
                context.namespace,
                document,
                events=events,
                context=context,
            )
            for _ in range(2)
        ]
        reports = [future.result(timeout=30) for future in futures]
    assert sum(report["seeded_count"] for report in reports) == 5
    assert reports[0]["seed_id"] == reports[1]["seed_id"]
    assert counts(database) == (5, 5, 3)


def test_adapter_reports_dependency_failure(tmp_path, monkeypatch, context):
    path = tmp_path / "skus.json"
    path.write_text(json.dumps(manifest(context.namespace)))
    monkeypatch.setenv("INVENTORY_DATABASE_URL", "explicit-unused-test-url")

    def unavailable(*args, **kwargs):
        raise storage_unavailable()

    monkeypatch.setattr(adapter, "seed_inventory", unavailable)
    result = adapter.inventory_seed(
        Invocation("inventory seed", {"sku_manifest": path}, None, "unit", context.namespace)
    )
    assert result.code == ExitCode.DEPENDENCY_FAILURE


def test_real_adapter_seeds_from_catalogue_manifest(
    database, events, context, tmp_path, monkeypatch
):
    path = tmp_path / "skus.json"
    path.write_text(json.dumps(manifest(context.namespace)))
    cache = tmp_path / "schema-cache.json"
    cache.write_text(
        json.dumps(
            {
                "compatibility": "BACKWARD_TRANSITIVE",
                "schemas": list(offline_cache().entries.values()),
            }
        )
    )
    monkeypatch.setenv("EVENT_SCHEMA_CACHE_PATH", str(cache))
    monkeypatch.setattr(sdk, "_publisher", None)
    invocation = Invocation(
        "inventory seed",
        {"sku_manifest": path, "profile": "performance", "seed": 42},
        None,
        "adapter-live",
        context.namespace,
    )
    result = adapter.inventory_seed(invocation)
    assert result.code == ExitCode.COMPLETED, result.reasons
    assert json.loads(result.reasons[0])["seeded_count"] == 3
    assert counts(database) == (3, 3, 1)
    assert json.loads(adapter.inventory_seed(invocation).reasons[0])["seeded_count"] == 0


@pytest.mark.parametrize(
    "field,value",
    [("seed", True), ("seed", -1), ("default_on_hand", 0), ("default_on_hand", 2**63)],
)
def test_invalid_seed_profile_is_rejected_before_database_access(context, field, value):
    with pytest.raises(ValueError):
        seeding.seed_inventory(
            None,
            context.namespace,
            manifest(context.namespace),
            events=None,
            context=context,
            **{field: value},
        )
