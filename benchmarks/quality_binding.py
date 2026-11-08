"""Explicit W-QUALITY composition. Missing owner proofs block all publication.

PROJECTCTL_ADAPTER_MODULE=benchmarks.quality_binding registers this factory plus
the existing Prompt 3 composition. Live resource/namespace/seed and read-only
role review slots deliberately have no fabricated defaults.
"""

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from benchmarks.collectors import GoldVisibilityReader, SelfResourceReader, collector
from benchmarks.composition import catalog_projection
from benchmarks.dataset_checks import inspect_source
from benchmarks.experiment import ExperimentBindings
from benchmarks.observation import ObservationConfig, ObservationSession
from benchmarks.quality_audit import reconcile_quality
from benchmarks.quality_publisher import QualityDriver, QualityPublisher
from benchmarks.workloads import generate_workload
from projectctl.artifacts import file_hash, write_json
from projectctl.config import repo_path
from projectctl.providers import DependencyError


@dataclass(frozen=True)
class QualityOwners:
    fresh_namespace: object = None
    seed_audit: object = None
    sources_factory: object = None  # (context) -> QualitySources with read-only connect
    collectors_factory: object = None  # (context) -> declared SUT resource collectors
    review_path: object = None
    schema_cache_path: object = None
    registry_url: object = None
    bootstrap_servers: object = None
    cleanup: object = None


def verify_review(path):
    if path is None:
        raise DependencyError("quality read-only evidence mapping review unavailable")
    review = json.loads(repo_path(str(path)).read_text(encoding="utf-8"))
    required = {
        "benchmarks/quality_binding.py",
        "benchmarks/quality_sources.py",
        "benchmarks/quality_audit.py",
        "benchmarks/quality_publisher.py",
        "benchmarks/quality.py",
        "benchmarks/workloads.py",
        "benchmarks/quality_trial.py",
        "pipelines/ingestion/quality.py",
        "pipelines/storage/readers.py",
        "pipelines/curation/sink_observations.py",
        "pipelines/storage/publication.py",
        "pipelines/ingestion/bronze.py",
        "shared/event_transport/codec.py",
        "shared/event_transport/schemas.py",
        "shared/event_transport/consumer.py",
    }
    if (
        review.get("schema_version") != 1
        or set(review.get("reviewers", [])) != {"Jaineel", "Harsh", "Aditya", "Vichitr"}
        or review.get("read_only_audit") is not True
        or review.get("namespace_scoped") is not True
        or not required <= {ref["path"] for ref in review.get("contracts", [])}
    ):
        raise DependencyError("quality binding requires affected-owner read-only mapping review")
    for ref in review["contracts"]:
        if file_hash(repo_path(ref["path"])) != ref["sha256"]:
            raise DependencyError("reviewed quality binding bytes changed")
    return review


class QualityLifecycle:
    def __init__(self, config, owners, projection, *, gate="T-03"):
        if gate not in {"T-03", "G1"}:
            raise ValueError("explicit quality gate required")
        self.gate = gate
        self.counts = (
            {"planned": 100000, "unique_valid": 98500, "duplicate_deliveries": 1000, "invalid": 500}
            if gate == "T-03"
            else {"planned": 3, "unique_valid": 1, "duplicate_deliveries": 1, "invalid": 1}
        )
        self.config, self.owners, self.projection = config, owners, projection
        self.driver = QualityDriver(self.publish)
        self.publisher = self.sources = None

    async def publish(self, packet, context):
        if self.publisher is None:
            raise DependencyError("quality transport not validated")
        return await self.publisher(packet, context)

    async def prepare(self, context, manifest):
        if not re.fullmatch(r"bench-[a-z0-9][a-z0-9-]{0,55}", context["namespace"]) or re.match(
            r"bench-(dev|live|prod|production)(-|$)", context["namespace"]
        ):
            raise DependencyError("fresh isolated quality namespace required")
        if (
            any(
                getattr(self.owners, key) is None
                for key in (
                    "fresh_namespace",
                    "seed_audit",
                    "sources_factory",
                    "collectors_factory",
                )
            )
            or self.projection is None
        ):
            raise DependencyError(
                "quality setup/seed/read-only evidence callbacks or manifests missing"
            )
        review = verify_review(self.owners.review_path)
        write_json(Path(context["evidence_directory"]) / "quality_binding_review.json", review)
        report = await asyncio.to_thread(inspect_source, repo_path(self.config.dataset.source_path))
        write_json(Path(context["evidence_directory"]) / "source_checks.json", report)
        if report["status"] != "PASS":
            raise DependencyError("independent exact-source checks failed")
        frozen = generate_workload("W-QUALITY", context["seed"], self.projection).as_dict()
        if manifest["selected_skus"] != frozen["selected_skus"]:
            raise DependencyError("quality SKU selection differs from verified frozen recipe")
        seed = await self.owners.seed_audit(context)
        write_json(Path(context["evidence_directory"]) / "quality_seed_checks.json", seed)
        if any(
            type(seed.get(key)) is not type(value) or seed[key] != value
            for key, value in {
                "dataset_revision": self.projection["dataset_revision"],
                "active_sku_count": 19920,
                "projected_sku_count": 19920,
                "initial_on_hand": 10000,
                "reserved": 0,
                "stock_version": 1,
                "pending_outbox": 0,
                "deferred": 0,
            }.items()
        ):
            raise DependencyError("complete independent seed/projection proof unavailable")
        if (
            not isinstance(seed.get("namespace"), str)
            or not re.fullmatch(r"bench-[a-z0-9][a-z0-9-]{0,55}", seed["namespace"])
            or not isinstance(seed.get("run_id"), str)
            or not seed["run_id"]
        ):
            raise DependencyError("seed/projection evidence namespace and run provenance missing")
        proof = await self.owners.fresh_namespace(context)
        write_json(Path(context["evidence_directory"]) / "quality_setup.json", proof)
        required = (
            "created_new",
            "postgresql_real",
            "kafka_real",
            "registry_real",
            "locked_environment",
            "benchmark_mode",
            "quality_topics_empty",
            "analytics_namespace_empty",
        )
        if (
            proof.get("namespace") != context["namespace"]
            or proof.get("run_id") != context["run_id"]
            or any(proof.get(name) is not True for name in required)
            or proof.get("resource_profile") != self.config.profile.model_dump()
            or proof.get("effective_parameters") != context["parameters"]
        ):
            raise DependencyError("real isolated locked quality setup not established")
        from pipelines.ingestion.quality import QualityMaterializer
        from shared.event_transport.codec import EventCodec
        from shared.event_transport.schemas import SchemaCache

        cache = SchemaCache.load(self.owners.schema_cache_path)
        with httpx.Client(base_url=self.owners.registry_url, timeout=5, trust_env=False) as client:
            await asyncio.to_thread(cache.verify_online, client)
        codec = EventCodec(cache)
        self.driver.materializer = QualityMaterializer(
            codec,
            selected_skus=manifest["selected_skus"],
            dataset_revision=self.projection["dataset_revision"],
        )
        self.publisher = QualityPublisher(codec, self.owners.bootstrap_servers)
        context.update(
            selected_skus=manifest["selected_skus"],
            dataset_revision=self.projection["dataset_revision"],
            quality_topics=[
                context["namespace"] + "." + domain + ".v1"
                for domain in (
                    ("inventory-events", "retrieval-events", "conversation-events")
                    if self.gate == "T-03"
                    else ("inventory-events",)
                )
            ],
        )
        self.sources = self.owners.sources_factory(context)
        return proof

    async def validate(self, context, manifest):
        if self.publisher is None or self.sources is None:
            raise DependencyError("quality dependencies not prepared")
        rows = await asyncio.to_thread(self.sources.receipt_rows, context["namespace"])
        if rows:
            raise DependencyError("quality namespace contains prior source receipts")
        if manifest["expected_counts"] != self.counts:
            raise DependencyError("complete 100000-record T-03 or separately named G1 required")
        lag = self.sources.lag
        if lag.group != context["namespace"] + ".analytics.v1" or sorted(lag.partitions) != sorted(
            (topic, 0) for topic in context["quality_topics"]
        ):
            raise DependencyError(
                "quality offsets must observe the actual B0 worker and input topics"
            )

    async def drain(self, context, remaining_seconds):
        deadline = time.monotonic() + remaining_seconds
        await self.publisher.close()
        while time.monotonic() < deadline:
            rows = await asyncio.to_thread(self.sources.receipt_rows, context["namespace"])
            lag = await self.sources.lag(0)
            # The authoritative final export re-reads receipt observations from
            # zero after drain. Missing offsets and visibility never count as zero.
            if (
                len(rows) == self.counts["planned"]
                and all(
                    r["disposition"] == "invalid" or r["gold_visible_at"] is not None for r in rows
                )
                and len(lag) == len(self.sources.lag.series)
                and all(reading.value == 0 for reading in lag.values())
            ):
                return
            await asyncio.sleep(min(0.25, max(0, deadline - time.monotonic())))
        raise DependencyError("quality receipt/offset/visibility drain deadline exceeded")

    async def audit(self, context, directory):
        # Revalidate pinned code immediately before adopting the read-only export.
        verify_review(self.owners.review_path)
        observed = await asyncio.to_thread(self.sources.export, context)
        observed["binding_review_verified"] = True
        write_json(directory / "quality_raw_audit.json", observed)
        return reconcile_quality(context, directory, observed, gate=self.gate)

    def observer(self, context, directory, kind):
        async def active():
            return await asyncio.to_thread(self.sources.active, context["namespace"])

        gold = GoldVisibilityReader(active, directory, context["namespace"])
        return QualityObservationSession(
            ObservationConfig(
                directory=directory,
                run_id=context["run_id"],
                namespace=context["namespace"],
                workload="W-QUALITY" if self.gate == "T-03" else "G1",
                variant=context["variant_id"],
                evidence_kind=kind,
                stop=asyncio.Event(),
                collectors=(
                    collector("generator", SelfResourceReader()),
                    collector("kafka", self.sources.lag),
                    collector("gold", gold),
                    *self.owners.collectors_factory(context),
                ),
            ),
            publisher=self.publisher,
        )


class QualityObservationSession(ObservationSession):
    def __init__(self, config, *, publisher):
        super().__init__(config)
        self.publisher = publisher

    async def __aexit__(self, *args):
        # Also close on scheduling/drain/audit failures; no leaked producer on an
        # incomplete run. The SDK keeps an uncertain admission visibly unknown.
        try:
            return await super().__aexit__(*args)
        finally:
            await self.publisher.close()


def build_quality_bindings(config, *, owners=None):
    owners = owners or QualityOwners(
        schema_cache_path=os.environ.get("EVENT_SCHEMA_CACHE_PATH"),
        registry_url=os.environ.get("SCHEMA_REGISTRY_URL"),
        bootstrap_servers=os.environ.get("KAFKA_BOOTSTRAP_SERVERS"),
    )
    reasons = [
        f"quality owner {name} unavailable"
        for name in owners.__dataclass_fields__
        if name != "cleanup" and getattr(owners, name) is None
    ]
    projection = catalog_projection(config)
    if projection is None:
        reasons.append("verified Harsh canonical/SKU manifests unavailable")
    lifecycle = QualityLifecycle(config, owners, projection)
    return ExperimentBindings(
        mode="real",
        driver=lifecycle.driver,
        catalog_manifest=projection,
        prepare=lifecycle.prepare,
        validate=lifecycle.validate,
        drain=lifecycle.drain,
        audit=lifecycle.audit,
        observer_factory=lifecycle.observer,
        dependency_reasons=tuple(reasons),
        cleanup=owners.cleanup,
    )


def register(registry):
    """Backward-compatible module entry point for the unified composition."""
    from projectctl.jaineel import register as register_existing

    register_existing(registry)
