"""Jaineel's lifecycle orchestration over existing owner APIs, with explicit gaps.

OwnerCallbacks are harness handoff slots, not claimed exports from owner modules.
None is intentional until an owner supplies a scoped, reviewed implementation.
"""

import asyncio
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from benchmarks.collectors import SelfResourceReader, collector
from benchmarks.dataset_checks import inspect_source
from benchmarks.drivers import (
    CheckoutDriver,
    ImportDriver,
    IntegratedDriver,
    PipelineDriver,
    QueryDriver,
    SearchDriver,
)
from benchmarks.experiment import ExperimentBindings
from benchmarks.http_adapters import CatalogRequests, ConversationRequests, OrdersRequests
from benchmarks.observation import ObservationConfig, ObservationSession
from benchmarks.scheduler import journal, utc_now
from projectctl.artifacts import content_hash, file_hash, write_json
from projectctl.config import repo_path
from projectctl.models import ExitCode
from projectctl.providers import DependencyError, Invocation


@dataclass(frozen=True)
class OwnerCallbacks:
    # Async callbacks. No default returns created_new, drained, audited or seeded.
    fresh_namespace: object = None  # (context) -> namespace/run_id/created_new
    seed_audit: object = None  # (context) -> initial stock/projection/outbox proof
    drain: object = None  # (context, remaining_seconds) -> None
    audit: object = None  # (context, directory) -> independently reconciled result
    observer_factory: object = None  # complete SUT observation, when applicable
    layout_for: object = None  # frozen manifest selected by analytics variant
    query_day: object = None  # frozen UTC query day, never inferred from publication time
    templates: tuple = ()  # reviewed checkout/integrated request templates
    fault: object = None
    performance_review_path: str | None = None
    cleanup: object = None  # (context) -> stop owned runtime, also after failed prepare/validate


def catalog_projection(config):
    """Use Harsh's verified projection, then enforce consumer provenance/bounds."""
    from pipelines.catalog.adapter import runner_catalog_manifest
    from shared.contracts.catalog import NormalizedCatalogManifest, SkuManifest

    if not config.dataset.sku_manifest:
        return None
    path = repo_path(config.dataset.sku_manifest)
    document = json.loads(path.read_text(encoding="utf-8"))
    SkuManifest.model_validate(document)
    projection = runner_catalog_manifest(path)
    skus = projection["active_skus"]
    if (
        projection["source_sha256"] != config.dataset.expected_sha256
        or projection["rules_version"] != config.dataset.rules_version
        or len(skus) != 19920
        or document.get("sku_count") != len(skus)
        or skus != sorted(set(skus))
        or any(not sku.startswith("FK-") for sku in skus)
    ):
        raise DependencyError("verified SKU projection differs from the frozen source/rules/count")
    if not config.dataset.canonical_manifest:
        raise DependencyError("canonical manifest required to verify SKU provenance")
    normalized = json.loads(
        repo_path(config.dataset.canonical_manifest).read_text(encoding="utf-8")
    )
    NormalizedCatalogManifest.model_validate(normalized)
    if (
        normalized.get("content_sha256") != content_hash(normalized)
        or normalized.get("dataset_revision") != projection["dataset_revision"]
        or normalized.get("canonical_business_digest") != document.get("canonical_business_digest")
        or normalized["rules_version"] != config.dataset.rules_version
        or normalized["active_rows"] != 19920
        or any(
            entry["product_id"] != entry["sku"] or entry["sku"] != "FK-" + entry["source_pid"]
            for entry in document["sorted_skus"]
        )
    ):
        raise DependencyError("SKU and normalized manifest provenance differ")
    return projection


class Lifecycle:
    def __init__(self, workload, config, registry, owners):
        self.workload, self.config, self.registry, self.owners = workload, config, registry, owners
        self.transport = None

    def output(self, context):
        return repo_path(self.config.artifacts.root) / "setup" / context["namespace"]

    def arguments(self, context):
        out = self.output(context)
        return {
            "namespace": context["namespace"],
            "source": self.config.dataset.source_path,
            "rules": self.config.dataset.rules_version,
            "load_mode": context["parameters"]["catalog_load_mode"],
            "out": out.relative_to(repo_path(".")).as_posix(),
            "manifest": (out / "normalized_manifest.json").relative_to(repo_path(".")).as_posix(),
            "sku_manifest": (out / "sku_manifest.json").relative_to(repo_path(".")).as_posix(),
            "profile": "performance",
            "seed": context["seed"],
            "timeout_seconds": 120,
        }

    async def action(self, action, context):
        result = await asyncio.to_thread(
            self.registry.invoke,
            Invocation(
                action,
                self.arguments(context),
                self.config,
                context["run_id"],
                context["namespace"],
            ),
        )
        with (Path(context["evidence_directory"]) / "owner_setup.jsonl").open(
            "a", encoding="utf-8"
        ) as stream:
            journal(
                stream,
                {
                    "action": action,
                    "at": utc_now(),
                    "code": int(result.code),
                    "test_mode": result.test_mode,
                    "reasons": result.reasons,
                },
            )
        if result.code != ExitCode.COMPLETED or result.test_mode != "real":
            raise DependencyError(f"real owner setup incomplete: {action}")

    async def prepare(self, context, manifest):
        namespace = context["namespace"]
        if not re.fullmatch(r"bench-[a-z0-9][a-z0-9-]{0,55}", namespace) or re.match(
            r"bench-(dev|live|prod|production)(-|$)", namespace
        ):
            raise DependencyError("fresh isolated benchmark namespace required")
        if self.owners.fresh_namespace is None:
            raise DependencyError("owner fresh_namespace callback unavailable; no reset attempted")
        report = await asyncio.to_thread(inspect_source, repo_path(self.config.dataset.source_path))
        write_json(Path(context["evidence_directory"]) / "source_checks.json", report)
        if report["status"] != "PASS":
            raise DependencyError("independent exact-source checks incomplete or failed")
        proof = await self.owners.fresh_namespace(context)
        if (
            proof.get("namespace") != namespace
            or proof.get("run_id") != context["run_id"]
            or proof.get("created_new") is not True
        ):
            raise DependencyError("owner did not prove a fresh namespace for this run")
        # ImportDriver itself calls the real importer, including owner-local migrations.
        if self.workload in {"W-SEARCH", "W-CHECKOUT", "W-INTEGRATED"}:
            await self.action("db migrate", context)
            await self.action("catalog import", context)
            await self.action("catalog verify", context)
            generated = self.config.model_copy(deep=True)
            arguments = self.arguments(context)
            generated.dataset.sku_manifest = arguments["sku_manifest"]
            generated.dataset.canonical_manifest = arguments["manifest"]
            projection = catalog_projection(generated)
            write_json(Path(context["evidence_directory"]) / "catalog_projection.json", projection)
            if self.owners.seed_audit is None:
                raise DependencyError("independent seed/projection audit callback unavailable")
            await self.action("inventory seed", context)
            # Never measure search before the real stock consumer barrier and ANALYZE.
            await self.action("projection wait", context)
            seed = await self.owners.seed_audit(context)
            write_json(Path(context["evidence_directory"]) / "seed_checks.json", seed)
            if any(
                type(seed.get(name)) is not type(wanted) or seed[name] != wanted
                for name, wanted in {
                    "namespace": namespace,
                    "run_id": context["run_id"],
                    "active_sku_count": 19920,
                    "projected_sku_count": 19920,
                    "initial_on_hand": 10000,
                    "reserved": 0,
                    "stock_version": 1,
                    "pending_outbox": 0,
                    "deferred": 0,
                }.items()
            ):
                raise DependencyError("complete initial stock/projection/outbox proof missing")
        if self.transport is not None:
            await self.transport.prepare(context, manifest, catalog_projection(self.config))
        return proof

    async def validate(self, context, manifest):
        if self.workload == "W-SEARCH":
            if (
                os.environ.get("CATALOG_MAX_CONNECTIONS") != "4"
                or os.environ.get("CATALOG_REUSE_CONNECTIONS", "false").lower() != "false"
            ):
                raise DependencyError("frozen catalogue requires pool=4 and session reuse=false")
        if self.workload == "W-ANALYTICS" and (
            self.owners.layout_for is None or self.owners.query_day is None
        ):
            raise DependencyError("owner-pinned analytics layout manifest unavailable")

    async def drain(self, context, remaining_seconds):
        if self.transport is not None:
            await self.transport.close()
        if self.workload == "W-IMPORT":
            # A returned importer report acknowledges final promotion/export, not Kafka.
            await self.action("catalog verify", context)
        elif self.owners.drain is None:
            raise DependencyError("owner downstream drain callback unavailable")
        else:
            await self.owners.drain(context, remaining_seconds)

    async def audit(self, context, directory):
        if self.workload == "W-IMPORT":
            from benchmarks.import_audit import audit_import

            return await asyncio.to_thread(
                audit_import,
                repo_path(self.config.dataset.source_path),
                self.output(context),
                context["namespace"],
                directory,
            )
        if self.owners.audit is None:
            raise DependencyError("independent owner audit exports unavailable")
        result = await self.owners.audit(context, directory)
        if result.get("test_mode") != "real":
            raise DependencyError("real lifecycle cannot consume a test-double audit")
        return result

    def observer(self, context, directory, kind):
        if self.workload != "W-IMPORT":
            if self.owners.observer_factory is None:
                raise DependencyError("complete owner SUT observer unavailable")
            observer = self.owners.observer_factory(context, directory, kind)
            return (
                ClosingObserver(observer, self.transport)
                if self.transport is not None
                else observer
            )
        return ObservationSession(
            ObservationConfig(
                directory=directory,
                run_id=context["run_id"],
                namespace=context["namespace"],
                workload=self.workload,
                variant=context["variant_id"],
                evidence_kind=kind,
                collectors=(collector("generator", SelfResourceReader()),),
                stop=asyncio.Event(),
            )
        )


class ClosingObserver:
    """Close the SDK publisher on schedule, drain, observer and audit failures too."""

    def __init__(self, observer, transport):
        self.observer, self.transport = observer, transport
        self.config = observer.config

    async def __aenter__(self):
        try:
            return await self.observer.__aenter__()
        except BaseException:
            await self.transport.close()
            raise

    async def __aexit__(self, *args):
        try:
            return await self.observer.__aexit__(*args)
        finally:
            await self.transport.close()


def build_bindings(workload, config, *, registry, owners=None):
    """Missing owner slots are dependencies, never green stand-ins or discovered APIs."""
    from analytics.queries.suite import QUERIES, runner_query_adapter
    from pipelines.catalog.adapter import runner_importer

    owners = owners or OwnerCallbacks()
    lifecycle = Lifecycle(workload, config, registry, owners)
    reasons = []
    if owners.fresh_namespace is None:
        reasons.append("owner fresh_namespace callback unavailable (all affected storage owners)")
    projection = catalog_projection(config)
    templates = ()
    if workload == "W-IMPORT":
        driver = ImportDriver(
            runner_importer(
                repo_path(config.dataset.source_path), repo_path(config.artifacts.root) / "setup"
            )
        )
    elif workload == "W-SEARCH":
        query_path = repo_path("contracts/fixtures/catalog/queries.json")
        if config.retrieval.query_sha256 and file_hash(query_path) != config.retrieval.query_sha256:
            raise DependencyError("query exact-byte SHA-256 differs from frozen configuration")
        queries = json.loads(query_path.read_text("utf-8"))
        templates = tuple(queries["queries"])
        if len(templates) != 50 or len({q["query_id"] for q in templates}) != 50:
            raise DependencyError("frozen 50-query fixture missing or duplicated")
        driver = SearchDriver(CatalogRequests())
        if owners.seed_audit is None:
            reasons.append("Aditya/Harsh complete seed/projection audit callback unavailable")
    elif workload == "W-ANALYTICS":
        templates = tuple({"query_id": query_id} for query_id in QUERIES)
        adapter = None
        query_lock = asyncio.Lock()

        async def query(body, context):
            nonlocal adapter
            if owners.layout_for is None or owners.query_day is None:
                raise DependencyError("owner-pinned analytics layout manifest unavailable")
            # The owner adapter has one DuckDB connection. Queries run sequentially.
            async with query_lock:
                if adapter is None:
                    adapter = runner_query_adapter(
                        owners.layout_for,
                        os.environ.get("LAKEHOUSE_ROOT", "artifacts/lakehouse"),
                        owners.query_day,
                    )
                return await adapter(body, context)

        driver = QueryDriver(query)
        if owners.layout_for is None or owners.query_day is None:
            reasons.append("Harsh/Vichitr frozen analytics snapshot/layout binding unavailable")
    elif workload == "W-PIPE":
        from benchmarks.pipeline_transport import PipelineTransport

        lifecycle.transport = PipelineTransport()
        driver = PipelineDriver(lifecycle.transport.materialize, lifecycle.transport)
        for name in ("EVENT_SCHEMA_CACHE_PATH", "SCHEMA_REGISTRY_URL", "KAFKA_BOOTSTRAP_SERVERS"):
            if not os.environ.get(name):
                reasons.append("W-PIPE transport configuration unavailable: " + name)
    elif workload in {"W-CHECKOUT", "W-INTEGRATED"}:
        templates = tuple(owners.templates)
        driver = (
            CheckoutDriver(CatalogRequests(), OrdersRequests())
            if workload == "W-CHECKOUT"
            else IntegratedDriver(ConversationRequests())
        )
        if not templates:
            reasons.append("reviewed fixed cart/search/payment templates unavailable")
        if owners.seed_audit is None:
            reasons.append("Aditya/Harsh complete seed/projection audit callback unavailable")
    else:
        raise ValueError("workload has no reviewed real driver composition")
    if workload != "W-IMPORT":
        for name in ("drain", "audit", "observer_factory"):
            if getattr(owners, name) is None:
                reasons.append(f"owner {name} callback unavailable for {workload}")
    return ExperimentBindings(
        mode="real",
        driver=driver,
        catalog_manifest=projection,
        templates=templates,
        prepare=lifecycle.prepare,
        validate=lifecycle.validate,
        drain=lifecycle.drain,
        audit=lifecycle.audit,
        observer_factory=lifecycle.observer,
        dependency_reasons=tuple(reasons),
        fault=owners.fault,
        performance_review_path=owners.performance_review_path,
        cleanup=owners.cleanup,
    )
