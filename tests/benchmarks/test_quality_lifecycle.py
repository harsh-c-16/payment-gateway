"""Explicit setup/registry/reader doubles exercise lifecycle controls only."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

from benchmarks.quality_binding import QualityLifecycle, QualityOwners, verify_review
from benchmarks.quality_trial import run_g1
from benchmarks.workloads import generate_workload
from projectctl.config import load_config
from projectctl.providers import DependencyError


@pytest.mark.parametrize("fault", [None, "seed_version", "seed_scope", "setup", "selection"])
def test_quality_preparation_adopts_only_frozen_verified_inputs(tmp_path, monkeypatch, fault):
    config = load_config()
    projection = {
        "active_skus": [f"FK-TEST-{i:05}" for i in range(19920)],
        "dataset_revision": "offline-registry-and-catalog-double",
    }
    manifest = generate_workload("W-QUALITY", 42, projection).as_dict()
    ctx = {
        "namespace": "bench-quality-lifecycle",
        "seed": 42,
        "run_id": "00000000-0000-4000-8000-000000000001",
        "evidence_directory": str(tmp_path),
        "parameters": config.variants["B0"].config.model_dump(),
    }
    calls = []

    async def seed_double(context):
        calls.append("seed_audit")
        proof = {
            "namespace": "bench-reviewed-seed-double",
            "run_id": ctx["run_id"],
            "dataset_revision": projection["dataset_revision"],
            "active_sku_count": 19920,
            "projected_sku_count": 19920,
            "initial_on_hand": 10000,
            "reserved": 0,
            "stock_version": 1,
            "pending_outbox": 0,
            "deferred": 0,
        }
        if fault == "seed_version":
            proof["stock_version"] = True
        elif fault == "seed_scope":
            proof.pop("namespace")
        return proof

    async def fresh_double(context):
        calls.append("fresh_namespace")
        return {
            "namespace": ctx["namespace"],
            "run_id": ctx["run_id"],
            "created_new": True,
            "postgresql_real": True,
            "kafka_real": True,
            "registry_real": True,
            "locked_environment": True,
            "benchmark_mode": True,
            "quality_topics_empty": fault != "setup",
            "analytics_namespace_empty": True,
            "resource_profile": config.profile.model_dump(),
            "effective_parameters": ctx["parameters"],
        }

    def sources_double(context):
        calls.append("sources_factory")
        assert context["selected_skus"] == manifest["selected_skus"]
        assert len(context["quality_topics"]) == 3
        assert {topic.split(".")[1] for topic in context["quality_topics"]} == {
            "inventory-events",
            "retrieval-events",
            "conversation-events",
        }
        return object()

    monkeypatch.setattr("benchmarks.quality_binding.verify_review", lambda path: {"double": True})
    monkeypatch.setattr(
        "benchmarks.quality_binding.inspect_source", lambda path: {"status": "PASS"}
    )
    cache_double = SimpleNamespace(verify_online=lambda client: calls.append("verify_online"))
    monkeypatch.setattr(
        "shared.event_transport.schemas.SchemaCache.load", lambda path: cache_double
    )
    owners = QualityOwners(
        fresh_namespace=fresh_double,
        seed_audit=seed_double,
        sources_factory=sources_double,
        collectors_factory=lambda ctx: (),
        review_path="offline-double",
        schema_cache_path="offline-double",
        registry_url="http://registry.test",
        bootstrap_servers="offline-double",
    )
    lifecycle = QualityLifecycle(config, owners, projection)
    if fault == "selection":
        manifest["selected_skus"] = list(reversed(manifest["selected_skus"]))
    if fault:
        with pytest.raises(DependencyError):
            asyncio.run(lifecycle.prepare(ctx, manifest))
        assert lifecycle.publisher is None  # No broker client after a failed proof.
    else:
        proof = asyncio.run(lifecycle.prepare(ctx, manifest))
        assert proof["created_new"] is True
        assert lifecycle.driver.materializer.skus == tuple(manifest["selected_skus"])
        assert calls == ["seed_audit", "fresh_namespace", "verify_online", "sources_factory"]


def test_unreviewed_mapping_is_not_an_approval():
    with pytest.raises(DependencyError, match="review unavailable"):
        verify_review(None)


def test_blocked_g1_records_not_run_without_setup_or_plan(tmp_path):
    called = []

    async def forbidden(ctx):
        called.append(ctx)
        pytest.fail("missing prerequisites must block setup")

    owners = replace(QualityOwners(), fresh_namespace=forbidden)
    out = tmp_path / "g1"
    result = asyncio.run(run_g1(load_config(), out, owners=owners))
    assert result["status"] == "NOT_RUN" and result["passed"] is None
    assert result["exit_code"] == 4 and called == []
    assert (out / "summary.json").exists() and not (out / "planned.jsonl").exists()


@pytest.mark.parametrize(
    "has_offset,visible,passes",
    [
        (True, True, True),
        (False, True, False),
        (True, False, False),
    ],
)
def test_drain_needs_complete_offsets_and_visibility(tmp_path, has_offset, visible, passes):
    class LagDouble:
        series = ("partition-double",)

        async def __call__(self, sequence):
            return {"partition-double": SimpleNamespace(value=0)} if has_offset else {}

    class SourcesDouble:
        lag = LagDouble()

        def receipt_rows(self, namespace):
            return [
                {
                    "disposition": "invalid" if i == 2 else "new_valid",
                    "gold_visible_at": "observed" if visible else None,
                }
                for i in range(3)
            ]

    class PublisherDouble:
        async def close(self):
            pass

    lifecycle = QualityLifecycle(load_config(), QualityOwners(), {}, gate="G1")
    lifecycle.sources, lifecycle.publisher = SourcesDouble(), PublisherDouble()
    if passes:
        asyncio.run(lifecycle.drain({"namespace": "bench-double"}, 0.05))
    else:
        with pytest.raises(DependencyError, match="drain deadline exceeded"):
            asyncio.run(lifecycle.drain({"namespace": "bench-double"}, 0.05))
