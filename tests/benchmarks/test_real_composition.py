"""Explicit lifecycle/registry doubles test ordering; none proves live integration."""

import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

import projectctl.artifacts as artifacts
import projectctl.config as configuration
from benchmarks.composition import Lifecycle, OwnerCallbacks, build_bindings, catalog_projection
from benchmarks.experiment import run_experiment
from projectctl.artifacts import content_hash, write_json
from projectctl.config import load_config
from projectctl.providers import DependencyError, ProviderRegistry


def test_missing_callbacks_produce_saved_dependencies_without_prepare(tmp_path, monkeypatch):
    config = load_config()
    config.artifacts.root = "results"
    binding = build_bindings("W-IMPORT", config, registry=ProviderRegistry())

    async def forbidden(*args):
        pytest.fail("missing production callback must stop before preparation")

    binding = replace(binding, prepare=forbidden)
    monkeypatch.setattr(configuration, "ROOT", tmp_path)
    monkeypatch.setattr(artifacts, "ROOT", tmp_path)
    result = asyncio.run(
        run_experiment(
            "W-IMPORT",
            "I0",
            1,
            42,
            config=config,
            bindings=binding,
            evidence_kind="test",
        )
    )
    summary = json.loads((tmp_path / "results" / result["run_id"] / "summary.json").read_text())
    assert summary["exit_code"] == 4
    assert result["started_at"] is None and result["correctness_passed"] is None
    assert any("fresh_namespace callback unavailable" in reason for reason in summary["reasons"])
    assert all(metric["value"] is None for metric in summary["metrics"])


def test_import_driver_binds_current_source_and_output_root(monkeypatch):
    import pipelines.catalog.adapter as owner

    captured = []

    def importer_double(source, output):
        captured.append((source, output))
        return object()

    monkeypatch.setattr(owner, "runner_importer", importer_double)
    config = load_config()
    config.dataset.source_path = "data/raw/new-source.csv"
    config.artifacts.root = "artifacts/new-root"
    binding = build_bindings("W-IMPORT", config, registry=ProviderRegistry())
    assert binding.driver.importer is not None
    assert captured == [
        (
            configuration.repo_path("data/raw/new-source.csv"),
            configuration.repo_path("artifacts/new-root/setup"),
        )
    ]


def manifests(tmp_path, config):
    """Deterministic wire fixtures, no real import/database/stock claimed."""
    entries = [
        {
            "sku": f"FK-{i:05}",
            "product_id": f"FK-{i:05}",
            "source_pid": f"{i:05}",
            "source_observation_id": f"observation-{i}",
        }
        for i in range(19920)
    ]
    sku = {
        "schema_version": 1,
        "namespace": "bench-fixture",
        "dataset_revision": "fixture-revision",
        "source_sha256": config.dataset.expected_sha256,
        "rules_version": "flipkart-v1",
        "sku_count": 19920,
        "sorted_skus": entries,
        "canonical_business_digest": "a" * 64,
    }
    descriptor = {
        "path": "test.parquet",
        "sha256": "a" * 64,
        "byte_size": 1,
        "row_count": 1,
        "schema_name": "fixture",
        "schema_version": 1,
        "partition_values": {},
        "min_event_time": None,
        "max_event_time": None,
    }
    normalized = {
        "schema_version": 1,
        "dataset_revision": "fixture-revision",
        "source_manifest_ref": "a",
        "rules_version": "flipkart-v1",
        "dictionary_sha256": "a" * 64,
        "files": {key: descriptor for key in ("catalog", "observations", "dispositions", "issues")},
        "raw_rows": 20000,
        "canonical_rows": 19998,
        "active_rows": 19920,
        "inactive_rows": 78,
        "superseded_rows": 2,
        "rejected_rows": 0,
        "canonical_business_digest": "a" * 64,
    }
    sku["content_sha256"] = content_hash(sku)
    normalized["content_sha256"] = content_hash(normalized)
    write_json(tmp_path / "sku.json", sku)
    write_json(tmp_path / "normalized.json", normalized)
    config.dataset.sku_manifest = "sku.json"
    config.dataset.canonical_manifest = "normalized.json"
    return sku, normalized


@pytest.mark.parametrize("corruption", [None, "hash", "source", "count", "order", "revision"])
def test_projection_uses_owner_hash_verifier_and_rejects_wrong_provenance(
    tmp_path,
    monkeypatch,
    corruption,
):
    config = load_config()
    sku, normalized = manifests(tmp_path, config)
    if corruption == "source":
        sku["source_sha256"] = "b" * 64
    elif corruption == "count":
        sku["sorted_skus"].pop()
    elif corruption == "order":
        sku["sorted_skus"].reverse()
    elif corruption == "revision":
        normalized["dataset_revision"] = "another-revision"
    if corruption:
        sku["content_sha256"] = "0" * 64 if corruption == "hash" else content_hash(sku)
        normalized["content_sha256"] = content_hash(normalized)
        (tmp_path / "sku.json").write_text(json.dumps(sku), encoding="utf-8")
        (tmp_path / "normalized.json").write_text(json.dumps(normalized), encoding="utf-8")
    monkeypatch.setattr(configuration, "ROOT", tmp_path)
    if corruption:
        with pytest.raises((DependencyError, ValueError)):
            catalog_projection(config)
    else:
        projection = catalog_projection(config)
        assert len(projection["active_skus"]) == 19920
        assert projection["synthetic"] is False
        assert projection["sku_manifest_sha256"] == sku["content_sha256"]


def test_analytics_binds_owner_query_adapter_to_frozen_layout_and_day(monkeypatch, tmp_path):
    import analytics.queries.suite as owner

    calls = []

    def query_double(layout_for, root, day):
        calls.append((layout_for, root, day))

        async def query(body, context):
            return {"query_id": body["query_id"], "manifest": layout_for(context)}

        return query

    monkeypatch.setattr(owner, "runner_query_adapter", query_double)
    monkeypatch.setenv("LAKEHOUSE_ROOT", str(tmp_path))
    day = datetime(2026, 11, 7, tzinfo=UTC)

    def layout(context):
        return "pinned-generation-7"

    config = load_config()
    binding = build_bindings(
        "W-ANALYTICS",
        config,
        registry=ProviderRegistry(),
        owners=OwnerCallbacks(layout_for=layout, query_day=day),
    )

    async def exercise():
        first = await binding.driver.query_adapter({"query_id": "Q1"}, {})
        await binding.driver.query_adapter({"query_id": "Q2"}, {})
        return first

    assert asyncio.run(exercise())["manifest"] == "pinned-generation-7"
    assert calls == [(layout, str(tmp_path), day)]
    assert [t["query_id"] for t in binding.templates] == [f"Q{i}" for i in range(1, 7)]


def context(tmp_path):
    return {
        "namespace": "bench-prompt3-unit",
        "run_id": str(uuid4()),
        "seed": 42,
        "variant_id": "B0",
        "evidence_directory": str(tmp_path),
        "parameters": {"catalog_load_mode": "row"},
    }


@pytest.mark.parametrize("namespace", ["local-dev", "live", "bench-live", "bench-prod-x"])
def test_prepare_rejects_non_benchmark_namespaces_before_owner_calls(tmp_path, namespace):
    lifecycle = Lifecycle("W-IMPORT", load_config(), ProviderRegistry(), OwnerCallbacks())
    ctx = context(tmp_path) | {"namespace": namespace}
    with pytest.raises(DependencyError, match="isolated benchmark"):
        asyncio.run(lifecycle.prepare(ctx, {}))


def test_missing_fresh_owner_callback_never_resets_or_imports(tmp_path):
    lifecycle = Lifecycle("W-IMPORT", load_config(), ProviderRegistry(), OwnerCallbacks())
    with pytest.raises(DependencyError, match="fresh_namespace callback unavailable"):
        asyncio.run(lifecycle.prepare(context(tmp_path), {}))
    assert not (tmp_path / "owner_setup.jsonl").exists()


@pytest.mark.parametrize("bad_seed", [None, "stock_version", "boolean_version", "deferred"])
def test_search_setup_orders_real_barrier_after_seed_and_requires_strict_proof(
    tmp_path,
    monkeypatch,
    bad_seed,
):
    from projectctl.models import ExitCode
    from projectctl.providers import ProviderResult

    config = load_config()
    registry, calls = ProviderRegistry(), []
    ctx = context(tmp_path)
    expected_skus = [f"FK-FIXTURE-{i:05}" for i in range(19920)]

    def action_double(invocation):
        calls.append(invocation.action)
        assert invocation.namespace == ctx["namespace"]
        assert invocation.run_id == ctx["run_id"]
        assert invocation.arguments["namespace"] == ctx["namespace"]
        return ProviderResult(ExitCode.COMPLETED, ("explicit unit-test provider double",), "real")

    for action in (
        "db migrate",
        "catalog import",
        "catalog verify",
        "inventory seed",
        "projection wait",
    ):
        registry.register(action, action_double)

    async def fresh_double(context):
        calls.append("fresh_namespace")
        return {"namespace": context["namespace"], "run_id": context["run_id"], "created_new": True}

    async def seed_double(context):
        calls.append("independent seed audit")
        report = {
            "namespace": context["namespace"],
            "run_id": context["run_id"],
            "active_sku_count": 19920,
            "projected_sku_count": 19920,
            "initial_on_hand": 10000,
            "reserved": 0,
            "stock_version": 1,
            "pending_outbox": 0,
            "deferred": 0,
            "catalog_skus": expected_skus,
            "inventory_skus": expected_skus,
            "projected_skus": expected_skus,
        }
        if bad_seed == "boolean_version":
            report["stock_version"] = True
        elif bad_seed:
            report[bad_seed] = 2
        return report

    monkeypatch.setattr("benchmarks.composition.inspect_source", lambda path: {"status": "PASS"})
    monkeypatch.setattr(
        "benchmarks.composition.catalog_projection", lambda cfg: {"active_skus": expected_skus}
    )
    owners = OwnerCallbacks(fresh_namespace=fresh_double, seed_audit=seed_double)
    lifecycle = Lifecycle("W-SEARCH", config, registry, owners)
    if bad_seed:
        with pytest.raises(DependencyError, match="initial stock/projection/outbox"):
            asyncio.run(lifecycle.prepare(ctx, {}))
    else:
        proof = asyncio.run(lifecycle.prepare(ctx, {}))
        assert proof["created_new"] is True
    assert calls == [
        "fresh_namespace",
        "db migrate",
        "catalog import",
        "catalog verify",
        "inventory seed",
        "projection wait",
        "independent seed audit",
    ]
    assert [
        json.loads(line)["action"]
        for line in (tmp_path / "owner_setup.jsonl").read_text().splitlines()
    ] == calls[1:-1]


def test_partial_owner_migration_blocks_import_without_fallback(tmp_path, monkeypatch):
    from projectctl.models import ExitCode
    from projectctl.providers import ProviderResult

    registry = ProviderRegistry()
    registry.register(
        "db migrate",
        lambda invocation: ProviderResult(
            ExitCode.DEPENDENCY_FAILURE,
            ("analytics only; other owners NOT_RUN",),
            "real",
        ),
    )

    async def fresh_double(context):
        return {"namespace": context["namespace"], "run_id": context["run_id"], "created_new": True}

    monkeypatch.setattr("benchmarks.composition.inspect_source", lambda path: {"status": "PASS"})
    lifecycle = Lifecycle(
        "W-SEARCH",
        load_config(),
        registry,
        OwnerCallbacks(fresh_namespace=fresh_double),
    )
    with pytest.raises(DependencyError, match="db migrate"):
        asyncio.run(lifecycle.prepare(context(tmp_path), {}))
    rows = (tmp_path / "owner_setup.jsonl").read_text().splitlines()
    assert len(rows) == 1 and json.loads(rows[0])["code"] == 4


def test_import_observer_only_claims_actual_generator_resources(tmp_path):
    lifecycle = Lifecycle("W-IMPORT", load_config(), ProviderRegistry(), OwnerCallbacks())
    ctx = context(tmp_path)
    observer = lifecycle.observer(ctx, tmp_path, "test")
    assert observer.config.mode == "real"
    assert {s.component for c in observer.config.collectors for s in c.series} == {"generator"}
    assert observer.config.namespace == ctx["namespace"]
    assert observer.config.run_id == ctx["run_id"]


@pytest.mark.parametrize(
    "pool,reuse,accepted",
    [
        ("4", "false", True),
        ("10", "false", False),
        ("4", "true", False),
        (None, "false", False),
    ],
)
def test_search_readiness_checks_frozen_pool_and_no_session_reuse(
    tmp_path,
    monkeypatch,
    pool,
    reuse,
    accepted,
):
    if pool is None:
        monkeypatch.delenv("CATALOG_MAX_CONNECTIONS", raising=False)
    else:
        monkeypatch.setenv("CATALOG_MAX_CONNECTIONS", pool)
    monkeypatch.setenv("CATALOG_REUSE_CONNECTIONS", reuse)
    lifecycle = Lifecycle("W-SEARCH", load_config(), ProviderRegistry(), OwnerCallbacks())
    if accepted:
        asyncio.run(lifecycle.validate(context(tmp_path), {}))
    else:
        with pytest.raises(DependencyError, match="pool=4"):
            asyncio.run(lifecycle.validate(context(tmp_path), {}))
