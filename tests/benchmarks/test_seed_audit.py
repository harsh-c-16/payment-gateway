"""Explicit read-only SQL/callback doubles; no actual inventory/seed claim."""

import asyncio
from contextlib import contextmanager, nullcontext

import pytest

from benchmarks.seed_audit import (
    MEMBERSHIPS,
    collect_membership,
    verify_seed_membership,
    with_seed_membership,
)
from projectctl.providers import DependencyError


def test_equal_counts_with_a_substituted_sku_cannot_pass():
    projection = {"active_skus": ["FK-A", "FK-B", "FK-C"]}
    seed = {key: list(reversed(projection["active_skus"])) for key in MEMBERSHIPS}
    proof = verify_seed_membership(seed, projection)
    assert proof["status"] == "PASS" and proof["expected_count"] == 3
    seed["inventory_skus"][-1] = "FK-OTHER"
    with pytest.raises(DependencyError, match="differs.*inventory_skus"):
        verify_seed_membership(seed, projection)


@pytest.mark.parametrize("field", MEMBERSHIPS)
@pytest.mark.parametrize(
    "invalid", [None, [], ["FK-A", "FK-A"], ["FK-A", "bad space"], ["FK-A", 1]]
)
def test_missing_incomplete_or_duplicate_membership_cannot_be_a_count_only_pass(field, invalid):
    projection = {"active_skus": ["FK-A", "FK-B"]}
    seed = {key: list(projection["active_skus"]) for key in MEMBERSHIPS}
    seed[field] = invalid
    with pytest.raises(DependencyError, match="unique seed SKU lists"):
        verify_seed_membership(seed, projection)


@pytest.mark.parametrize("namespace", [None, "dev", "bench-dev", "bench-live-x", "other"])
def test_nonisolated_seed_membership_fails_before_any_connection(namespace, monkeypatch):
    def forbidden(_):
        pytest.fail("invalid namespace reached a read connection")

    monkeypatch.setattr("infra.analytics_runtime.read_connection", forbidden)
    with pytest.raises(DependencyError, match="isolated benchmark"):
        collect_membership(namespace)


def test_restricted_owner_reader_is_reused_with_bound_namespace_and_no_writes(monkeypatch):
    statements, connections = [], []

    class ReadDouble:
        def transaction(self):
            return nullcontext()

        def execute(self, statement, parameters=None):
            self.statement = statement
            statements.append((statement, parameters))
            assert statement.startswith(
                ("SET LOCAL statement_timeout", "SET TRANSACTION", "SELECT")
            )
            if statement.startswith("SELECT"):
                assert parameters == ("bench-seed-fixture",)
            return self

        def fetchall(self):
            if "DISTINCT" in self.statement:
                return [("original-seed-run",)]
            return [("FK-A",), ("FK-B",)]

        def fetchone(self):
            assert "published_at IS NULL" in self.statement
            return (0,)

    @contextmanager
    def reader(variable):
        connections.append(variable)
        yield ReadDouble()

    monkeypatch.setattr("infra.analytics_runtime.read_connection", reader)
    result = collect_membership("bench-seed-fixture")
    assert result == {field: ["FK-A", "FK-B"] for field in MEMBERSHIPS} | {
        "run_id": "original-seed-run",
        "pending_outbox": 0,
    }
    assert connections == ["INVENTORY_AUDIT_DATABASE_URL", "CATALOG_AUDIT_DATABASE_URL"]
    assert len([s for s, _ in statements if s.startswith("SELECT")]) == 5


def test_adapter_preserves_original_scope_and_audits_the_seed_namespace(monkeypatch):
    calls = []
    original = {
        "namespace": "bench-seed-fixture",
        "run_id": "original-seed-run",
        "pending_outbox": 0,
    }

    async def callback(context):
        calls.append(context)
        return dict(original)

    def collect(namespace):
        calls.append(namespace)
        return {field: ["FK-A"] for field in MEMBERSHIPS}

    monkeypatch.setattr("benchmarks.seed_audit.collect_membership", collect)
    wrapped = with_seed_membership(callback)
    assert calls == []
    context = {"namespace": "bench-new-measurement"}
    result = asyncio.run(wrapped(context))
    assert calls == [context, "bench-seed-fixture"]
    assert all(result[key] == value for key, value in original.items())


@pytest.mark.parametrize("field,value", [("run_id", "wrong-run"), ("pending_outbox", 1)])
def test_combined_seed_callback_cannot_override_inventory_evidence(monkeypatch, field, value):
    async def callback(context):
        return {"namespace": "bench-seed-fixture", "run_id": "seed-run", "pending_outbox": 0}

    def collect(namespace):
        return {key: ["FK-A"] for key in MEMBERSHIPS} | {
            "run_id": "seed-run",
            "pending_outbox": 0,
            field: value,
        }

    monkeypatch.setattr("benchmarks.seed_audit.collect_membership", collect)
    with pytest.raises(DependencyError, match="conflicts"):
        asyncio.run(with_seed_membership(callback)({}))


def test_real_select_only_role_reads_exact_keys_pending_rows_and_original_run(monkeypatch):
    import json
    import os
    from uuid import uuid4

    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo

    url = os.environ.get("INVENTORY_TEST_DATABASE_URL")
    if not url:
        pytest.skip("NOT_RUN: INVENTORY_TEST_DATABASE_URL required for read-only PostgreSQL audit")
    suffix = uuid4().hex
    schema, role = "seed_audit_" + suffix, "seed_reader_" + suffix
    namespace = "bench-seed-fixture"
    with psycopg.connect(url, autocommit=True) as admin:
        assert 180000 <= admin.info.server_version < 190000
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            admin.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            admin.execute("CREATE TABLE inventory(namespace text,sku text)")
            admin.execute("CREATE TABLE products(namespace text,sku text,active boolean)")
            admin.execute("CREATE TABLE stock_projection(namespace text,sku text)")
            admin.execute(
                "CREATE TABLE outbox(namespace text,payload bytea,published_at timestamptz)"
            )
            for sku in ("FK-A", "FK-B"):
                admin.execute("INSERT INTO inventory VALUES (%s,%s)", (namespace, sku))
                admin.execute("INSERT INTO products VALUES (%s,%s,true)", (namespace, sku))
                admin.execute("INSERT INTO stock_projection VALUES (%s,%s)", (namespace, sku))
            # Other namespaces and already-published rows must not inflate pending.
            for scope, published in (
                (namespace, None),
                ("bench-other", None),
                (namespace, "2026-11-11T00:00:00Z"),
            ):
                admin.execute(
                    "INSERT INTO outbox VALUES (%s,%s,%s)",
                    (scope, json.dumps({"run_id": "original-seed"}).encode(), published),
                )
            admin.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD 'ephemeral_seed_test_only'").format(
                    sql.Identifier(role)
                )
            )
            admin.execute(
                sql.SQL("ALTER ROLE {} SET default_transaction_read_only=on").format(
                    sql.Identifier(role)
                )
            )
            admin.execute(
                sql.SQL("ALTER ROLE {} SET search_path TO {}").format(
                    sql.Identifier(role), sql.Identifier(schema)
                )
            )
            admin.execute(
                sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                    sql.Identifier(schema), sql.Identifier(role)
                )
            )
            admin.execute(
                sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(
                    sql.Identifier(schema), sql.Identifier(role)
                )
            )
            reader_url = make_conninfo(url, user=role, password="ephemeral_seed_test_only")
            for variable in ("INVENTORY_AUDIT_DATABASE_URL", "CATALOG_AUDIT_DATABASE_URL"):
                monkeypatch.setenv(variable, reader_url)
            result = collect_membership(namespace)
            assert result == {key: ["FK-A", "FK-B"] for key in MEMBERSHIPS} | {
                "pending_outbox": 1,
                "run_id": "original-seed",
            }
            admin.execute(
                "INSERT INTO outbox VALUES (%s,%s,NULL)",
                (namespace, json.dumps({"run_id": "different-run"}).encode()),
            )
            with pytest.raises(DependencyError, match="original run ID"):
                collect_membership(namespace)
        finally:
            assert schema.startswith("seed_audit_") and role.startswith("seed_reader_")
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
            admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
