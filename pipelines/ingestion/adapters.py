"""Concrete M4 callbacks for the shared runner; independent audits stay in the harness."""

import asyncio
import math
from pathlib import Path
from time import monotonic

import psycopg
from confluent_kafka.admin import AdminClient

from benchmarks.collectors import KafkaLagReader
from benchmarks.composition import OwnerCallbacks
from benchmarks.observation import Series
from benchmarks.quality_sources import QualitySources, json_value
from benchmarks.runtime_observer import MetricsTarget, RuntimeObserver
from infra import streaming
from pipelines.curation.db import sink_lock
from pipelines.ingestion.lifecycle import assert_empty, isolated_namespace, reset_namespace
from pipelines.ingestion.receipts import migrate_analytics
from pipelines.storage.parquet import iter_verified
from pipelines.storage.publication import iter_membership
from pipelines.storage.readers import _wire, active_manifest


class AnalyticsSources(QualitySources):
    """Use existing read-only exports, allowing every declared business Gold table."""

    def active(self, namespace):
        from projectctl.artifacts import content_hash

        manifest = active_manifest(self.connect, namespace, "gold")
        with self.connect() as tx:
            members = list(iter_membership(tx, namespace, "gold", manifest.generation))
        tables = {}
        for file in manifest.files:
            tables.setdefault(file.schema_name, []).extend(
                _wire(json_value(row)) for row in iter_verified(self.store, file)
            )
        rows = [row for table in tables.values() for row in table]
        digest = content_hash(manifest.model_dump(mode="json"))
        return {
            "namespace": namespace,
            "generation": manifest.generation,
            "query_generation": manifest.generation,
            "manifest_sha256": digest,
            "query_manifest_sha256": digest,
            "membership_ids": members,
            "rows": rows,
            "tables": tables,
            "manifest": manifest.model_dump(mode="json"),
        }


class AnalyticsCallbacks:
    """Run this controller on Linux with the real shared FileStore mounted.

    read_connect must be an independently configured read-only database role.
    Deployment/resource/seed/business-audit inputs are explicit, never invented.
    """

    def __init__(self, pipeline, read_connect, deployment, *, bootstrap):
        if not callable(read_connect):
            raise TypeError("An explicit read-only analytics connection factory is required")
        self.pipeline, self.read_connect = pipeline, read_connect
        self.deployment, self.bootstrap = deployment, bootstrap

    def lag(self, context):
        self.deployment.check_context(context)
        topics = context.get("quality_topics") or context.get("analytics_topics")
        if topics is None and context.get("workload_id") == "W-PIPE":
            topics = [context["namespace"] + ".inventory-events.v1"]
        allowed = set(streaming.topic_names(context["namespace"]))
        if (
            not topics
            or len(set(topics)) != len(topics)
            or any(t not in allowed or t.endswith(".dead-letter.v1") for t in topics)
        ):
            raise ValueError("Declare the actual business input topics for this run")
        return KafkaLagReader(
            AdminClient({"bootstrap.servers": self.bootstrap}),
            context["namespace"] + ".analytics.v1",
            [(topic, p) for topic in topics for p in range(context["parameters"]["partitions"])],
        )

    def sources_factory(self, context):
        return AnalyticsSources(self.read_connect, self.pipeline.store, self.lag(context))

    def _prepare(self, context):
        self.deployment.check_context(context)
        namespace = isolated_namespace(context["namespace"])
        # Retained files must not be silently reused even if SQL was manually cleared.
        if any(
            (self.pipeline.store.root / kind / namespace).exists()
            for kind in ("bronze", "silver", "gold")
        ):
            raise ValueError("Fresh namespace has retained files; choose a new namespace")
        admin = AdminClient({"bootstrap.servers": self.bootstrap})
        if set(streaming.topic_names(namespace)) & set(admin.list_topics(timeout=10).topics):
            raise ValueError("Fresh namespace already has Kafka topics")
        with self.pipeline.connect() as tx, tx.transaction():
            migrate_analytics(tx)
            sink_lock(tx, namespace)
            assert_empty(tx, namespace)
        # Check the independent role before creating topics or starting writers.
        with self.read_connect() as tx:
            if tx.execute("SHOW default_transaction_read_only").fetchone()[0] != "on":
                raise ValueError("Evidence connection must default to read-only")
        streaming.provision_topics(
            namespace, context["parameters"]["partitions"], bootstrap=self.bootstrap
        )
        self.deployment.stage()
        try:
            self.deployment.start()
        except BaseException:
            self.deployment.stop()
            raise
        return {
            "namespace": namespace,
            "run_id": context["run_id"],
            "created_new": True,
            "test_mode": "real",
            "analytics_only": True,
            "partitions": context["parameters"]["partitions"],
            "consumers": context["parameters"]["consumers"],
        }

    async def fresh_namespace(self, context):
        return await asyncio.to_thread(self._prepare, context)

    async def drain(self, context, remaining_seconds):
        self.deployment.check_context(context)
        if (
            type(remaining_seconds) not in (int, float)
            or not math.isfinite(remaining_seconds)
            or not 0 < remaining_seconds <= 600
        ):
            raise ValueError("A bounded positive drain deadline is required")
        sources = self.sources_factory(context)
        deadline = monotonic() + remaining_seconds
        while monotonic() < deadline:
            readings = await asyncio.to_thread(sources.lag.read_sync)
            unfinished = await asyncio.to_thread(self._unfinished, sources, context["namespace"])
            if (
                len(readings) == len(sources.lag.series)
                and not unfinished
                and all(r.value == 0 for r in readings.values())
            ):
                return
            await asyncio.sleep(min(0.1, max(0, deadline - monotonic())))
        raise TimeoutError("Analytics source/offset/Gold/DLQ drain deadline exceeded")

    @staticmethod
    def _unfinished(sources, namespace):
        with sources.connect() as tx:
            return tx.execute(
                """SELECT
                (SELECT count(*) FROM source_receipts WHERE namespace=%s AND
                  (disposition IS NULL OR
                   (disposition<>'invalid' AND gold_visible_at IS NULL))) +
                (SELECT count(*) FROM export_pending WHERE namespace=%s) +
                (SELECT count(*) FROM outbox WHERE namespace=%s AND published_at IS NULL)""",
                (namespace,) * 3,
            ).fetchone()[0]

    async def export(self, context, directory):
        """Raw evidence only; the consumer computes independent pass/fail/counts."""
        from projectctl.artifacts import write_json

        evidence = await asyncio.to_thread(self.sources_factory(context).export, context)
        write_json(Path(directory) / "analytics_raw_evidence.json", evidence)
        return evidence

    async def read_active(self, context):
        self.deployment.check_context(context)
        sources = AnalyticsSources(self.read_connect, self.pipeline.store, None)
        return await asyncio.to_thread(sources.active, context["namespace"])

    def observer_factory(self, *, resource_factory, shared_host_clock=False):
        targets = tuple(
            MetricsTarget(
                f"analytics-worker-{index}",
                f"http://127.0.0.1:{18060 + index}/metrics",
                tuple(
                    Series(
                        "source_records_total",
                        f"analytics-worker-{index}",
                        "records",
                        (("pipeline", "analytics"), ("disposition", disposition)),
                    )
                    for disposition in (
                        "new_valid",
                        "duplicate_delivery",
                        "invalid",
                        "redelivery_noop",
                    )
                ),
            )
            for index in range(len(self.deployment.workers))
        )
        return RuntimeObserver(
            targets,
            lag_factory=self.lag,
            read_active=self.read_active,
            resource_factory=resource_factory,
            shared_host_clock=shared_host_clock,
        )

    def reset(self, context, *, evaluation_accepted, external_readers_closed):
        self.deployment.check_context(context)
        return reset_namespace(
            self.pipeline,
            context["namespace"],
            quiescent=self.deployment.quiescent() and external_readers_closed is True,
            evaluation_accepted=evaluation_accepted,
        )

    def reset_participant(self, invocation, *, evaluation_accepted, external_readers_closed):
        """Owner-local participant for a reviewed global reset coordinator."""
        from projectctl.models import ExitCode
        from projectctl.providers import ProviderResult

        try:
            if invocation.namespace != self.deployment.namespace:
                raise ValueError("Reset invocation names a different namespace")
            self.reset(
                self.deployment.context,
                evaluation_accepted=evaluation_accepted,
                external_readers_closed=external_readers_closed,
            )
        except (ValueError, RuntimeError, OSError, psycopg.Error) as exc:
            return ProviderResult(ExitCode.DEPENDENCY_FAILURE, (str(exc),), "real")
        return ProviderResult(
            ExitCode.COMPLETED, ("Only selected analytics namespace reset; files retained",), "real"
        )


class AnalyticsRunner:
    """Register before a run exists; allocate a concrete deployment when context arrives."""

    def __init__(
        self,
        pipeline,
        read_connect,
        *,
        bootstrap,
        worker_memory_mib,
        worker_cpu_cores,
        dedicated_stack=False,
    ):
        self.pipeline, self.read_connect, self.bootstrap = pipeline, read_connect, bootstrap
        self.memory, self.cpu, self.dedicated_stack = (
            worker_memory_mib,
            worker_cpu_cores,
            dedicated_stack,
        )
        self.runs = {}

    def for_run(self, context):
        from infra.analytics_deployment import AnalyticsDeployment

        key = (context["namespace"], context["run_id"])
        if key not in self.runs:
            deployment = AnalyticsDeployment(
                context,
                worker_memory_mib=self.memory,
                worker_cpu_cores=self.cpu,
                dedicated_stack=self.dedicated_stack,
            )
            self.runs[key] = AnalyticsCallbacks(
                self.pipeline, self.read_connect, deployment, bootstrap=self.bootstrap
            )
        self.runs[key].deployment.check_context(context)
        return self.runs[key]

    async def fresh_namespace(self, context):
        return await self.for_run(context).fresh_namespace(context)

    async def drain(self, context, remaining_seconds):
        return await self.for_run(context).drain(context, remaining_seconds)

    async def stop(self, context):
        await asyncio.to_thread(self.for_run(context).deployment.stop)

    async def export(self, context, directory):
        return await self.for_run(context).export(context, directory)

    def sources_factory(self, context):
        return self.for_run(context).sources_factory(context)

    async def fault(self, context, profile, spec):
        return await self.for_run(context).deployment.fault(context, profile, spec)

    def owner_callbacks(self, *, seed_audit, independent_audit, resource_factory):
        if not all(callable(f) for f in (seed_audit, independent_audit, resource_factory)):
            raise TypeError("Real owner audits and SUT resource collectors are required")

        def observer(context, directory, kind):
            factory = self.for_run(context).observer_factory(resource_factory=resource_factory)
            return factory(context, directory, kind)

        return OwnerCallbacks(
            fresh_namespace=self.fresh_namespace,
            seed_audit=seed_audit,
            drain=self.drain,
            audit=independent_audit,
            observer_factory=observer,
            fault=self.fault,
        )
