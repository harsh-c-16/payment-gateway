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
            statements.append((statement, parameters))
            assert statement.startswith(("SET LOCAL statement_timeout", "SELECT sku"))
            if statement.startswith("SELECT"):
                assert parameters == ("bench-seed-fixture",)
            return self

        def fetchall(self):
            return [("FK-A",), ("FK-B",)]

    @contextmanager
    def reader(variable):
        connections.append(variable)
        yield ReadDouble()

    monkeypatch.setattr("infra.analytics_runtime.read_connection", reader)
    result = collect_membership("bench-seed-fixture")
    assert result == {field: ["FK-A", "FK-B"] for field in MEMBERSHIPS}
    assert connections == ["INVENTORY_AUDIT_DATABASE_URL", "CATALOG_AUDIT_DATABASE_URL"]
    assert len([s for s, _ in statements if s.startswith("SELECT")]) == 3


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
