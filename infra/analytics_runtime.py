"""Real M4 input for PROJECTCTL_RUNTIME_MODULE=infra.analytics_runtime.

Private URLs, reviewed mappings and a feasible frozen profile are deployment
inputs. Importing/registering this module opens no connection and starts nothing.
"""

import asyncio
import json
import os
from contextlib import contextmanager
from pathlib import Path

import psycopg

from benchmarks.collectors import collector
from benchmarks.composition import OwnerCallbacks
from benchmarks.pipeline_audit import audit_pipeline
from benchmarks.quality_binding import QualityOwners, verify_review
from infra import streaming
from infra.analytics_resources import DockerResources
from pipelines.catalog.adapter import runner_catalog_manifest, seed_facts
from pipelines.ingestion.adapters import AnalyticsRunner
from pipelines.ingestion.lifecycle import isolated_namespace
from pipelines.ingestion.runtime import pipeline_from_env
from projectctl.artifacts import file_hash, write_json
from projectctl.providers import DependencyError
from projectctl.runtime import RuntimeBindings


@contextmanager
def read_connection(variable):
    url = os.environ.get(variable)
    if not url:
        from infra.audit_roles import database_url

        service = variable.removesuffix("_AUDIT_DATABASE_URL").lower()
        url = database_url(service)
    with psycopg.connect(url, autocommit=True, connect_timeout=5, options="-ctimezone=UTC") as tx:
        if tx.execute("SHOW default_transaction_read_only").fetchone()[0] != "on":
            raise DependencyError(variable + " must default to read-only")
        if (
            tx.execute(
                """SELECT bool_or(has_table_privilege(
                current_user,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE'))
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=current_schema() AND c.relkind IN ('r','p')"""
            ).fetchone()[0]
            is not False
        ):
            raise DependencyError(variable + " must use a role without table write privileges")
        yield tx


class TeamAnalyticsRuntime:
    def __init__(self):
        self.runners, self.resources = {}, {}

    def runner(self, context):
        key = (context["namespace"], context["run_id"])
        if key not in self.runners:
            budget = context["resource_profile"]["consumer_group_total"]
            self.runners[key] = AnalyticsRunner(
                pipeline_from_env(),
                lambda: read_connection("ANALYTICS_AUDIT_DATABASE_URL"),
                bootstrap=os.environ["KAFKA_BOOTSTRAP_SERVERS"],
                worker_memory_mib=budget["memory_mib"],
                worker_cpu_cores=budget["cpu_cores"],
            )
        return self.runners[key]

    async def cleanup(self, context):
        runner = self.runners.get((context["namespace"], context["run_id"]))
        if runner is not None:
            await runner.stop(context)

    def resource_readers(self, context):
        key = (context["namespace"], context["run_id"])
        if key in self.resources:
            return self.resources[key]
        deployment = self.runner(context).for_run(context).deployment
        targets = json.loads(os.environ.get("PROJECTCTL_SUT_CONTAINERS", "{}"))
        if (
            not isinstance(targets, dict)
            or set(targets) - set(context["resource_profile"]["services"])
            or "analytics" in targets
        ):
            raise DependencyError("SUT container map must use declared profile service names")
        readers = []
        for component in context["resource_profile"]["services"]:
            if component == "analytics":
                services = deployment.services
            elif component in targets:
                readers.append(DockerResources(targets[component], component))
                continue
            else:
                services = (component,)
            for service in services:
                container = deployment.command("ps", "--quiet", service).strip()
                name = (
                    (
                        "analytics-api"
                        if service.endswith("-api")
                        else "analytics-worker-" + service.rsplit("-", 1)[-1]
                    )
                    if component == "analytics"
                    else component
                )
                readers.append(DockerResources(container, name))
        if len({r.container for r in readers}) != len(readers):
            raise DependencyError("A SUT cgroup cannot be counted as multiple independent services")
        self.resources[key] = tuple(
            collector("resources-" + r.series[0].component, r) for r in readers
        )
        return self.resources[key]

    def resource_proof(self, context):
        readers = self.resource_readers(context)
        allocations = context["resource_profile"]["service_allocations"]
        totals = {}
        for item in readers:
            reader = item.read
            name = item.name.removeprefix("resources-")
            component = "analytics" if name.startswith("analytics-") else name
            cpu, memory = totals.get(component, (0, 0))
            totals[component] = (cpu + round(reader.cores * 1_000_000_000), memory + reader.memory)
        for name, allocation in allocations.items():
            if totals.get(name) != (
                round(allocation["cpu_cores"] * 1_000_000_000),
                allocation["memory_mib"] * 1024 * 1024,
            ):
                raise DependencyError(
                    "Actual container resources differ from frozen profile: " + name
                )
        return context["resource_profile"]

    async def fresh_namespace(self, context):
        runner = self.runner(context)
        proof = await runner.fresh_namespace(context)
        try:
            facts = await asyncio.to_thread(streaming.verify)
            if os.environ.get("BENCHMARK_MODE", "false").lower() != "true":
                raise DependencyError("An explicit isolated benchmark deployment is required")
            from infra import postgres

            if (
                os.environ.get("CODE_COMMIT")
                != postgres.command(["git", "rev-parse", "HEAD"]).strip()
                or postgres.command(["git", "status", "--porcelain"]).strip()
            ):
                raise DependencyError("Runtime requires the actual clean committed source revision")
            deployment = runner.for_run(context).deployment
            expected_lock = file_hash(postgres.ROOT / "uv.lock")
            for service in deployment.services:
                actual_lock = await asyncio.to_thread(
                    deployment.command,
                    "exec",
                    "-T",
                    service,
                    "python",
                    "-c",
                    "import hashlib,pathlib;"
                    "print(hashlib.sha256(pathlib.Path('/app/uv.lock').read_bytes()).hexdigest())",
                )
                if actual_lock.strip() != expected_lock:
                    raise DependencyError("Running analytics image has a different dependency lock")
            profile = await asyncio.to_thread(self.resource_proof, context)
            proof.update(
                postgresql_real=True,
                kafka_real=True,
                registry_real=True,
                locked_environment=True,
                benchmark_mode=True,
                quality_topics_empty=True,
                analytics_namespace_empty=True,
                resource_profile=profile,
                effective_parameters=context["parameters"],
            )
            write_json(Path(context["evidence_directory"]) / "m4_environment.json", facts)
            return proof
        except BaseException:
            await runner.stop(context)
            raise

    async def seed_audit(self, context):
        def read():
            namespace = isolated_namespace(os.environ["M4_SEED_NAMESPACE"])
            with read_connection("CATALOG_AUDIT_DATABASE_URL") as tx:
                facts = seed_facts(tx, namespace)
                revisions = tx.execute(
                    "SELECT DISTINCT dataset_revision FROM products WHERE namespace=%s AND active",
                    (namespace,),
                ).fetchall()
            with read_connection("INVENTORY_AUDIT_DATABASE_URL") as tx:
                stock = tx.execute(
                    """SELECT count(*),min(on_hand),max(on_hand),min(reserved),max(reserved),
                    min(stock_version),max(stock_version) FROM inventory WHERE namespace=%s""",
                    (namespace,),
                ).fetchone()
                pending = tx.execute(
                    "SELECT count(*) FROM outbox WHERE namespace=%s AND published_at IS NULL",
                    (namespace,),
                ).fetchone()[0]
                run_ids = tx.execute(
                    """SELECT DISTINCT convert_from(payload,'UTF8')::jsonb->>'run_id'
                    FROM outbox WHERE namespace=%s""",
                    (namespace,),
                ).fetchall()
            if (
                len(revisions) != 1
                or len(run_ids) != 1
                or not run_ids[0][0]
                or stock != (19920, 10000, 10000, 0, 0, 1, 1)
            ):
                raise DependencyError(
                    "Seed namespace lacks one exact initial inventory/revision/run"
                )
            projection = runner_catalog_manifest(context["dataset"]["sku_manifest"])
            if revisions[0][0] != projection["dataset_revision"]:
                raise DependencyError(
                    "Live catalogue revision differs from the pinned SKU manifest"
                )
            return facts | {
                "pending_outbox": pending,
                "run_id": run_ids[0][0],
                "dataset_revision": revisions[0][0],
            }

        return await asyncio.to_thread(read)

    async def drain(self, context, remaining_seconds):
        return await self.runner(context).drain(context, remaining_seconds)

    def sources_factory(self, context):
        return self.runner(context).sources_factory(context)

    def collectors_factory(self, context):
        return self.resource_readers(context)

    def observer(self, context, directory, kind):
        callback = (
            self.runner(context)
            .for_run(context)
            .observer_factory(resource_factory=self.resource_readers)
        )
        return callback(context, directory, kind)

    async def audit(self, context, directory):
        path = os.environ.get("ANALYTICS_BINDING_REVIEW_PATH")
        review = verify_review(path)
        required = {
            "benchmarks/pipeline_audit.py",
            "infra/analytics_runtime.py",
            "pipelines/ingestion/adapters.py",
            "infra/analytics_resources.py",
        }
        if not required <= {ref["path"] for ref in review["contracts"]}:
            raise DependencyError(
                "Reviewed mapping must include concrete runtime and W-PIPE projection"
            )
        observed = await self.runner(context).export(context, directory)
        binding = review | {"namespace": context["namespace"], "review_sha256": file_hash(path)}
        return audit_pipeline(context, directory, observed, review=binding)

    async def fault(self, context, profile, spec):
        return await self.runner(context).fault(context, profile, spec)


def runtime_bindings():
    runtime = TeamAnalyticsRuntime()
    return RuntimeBindings(
        workloads={
            "W-PIPE": OwnerCallbacks(
                fresh_namespace=runtime.fresh_namespace,
                drain=runtime.drain,
                audit=runtime.audit,
                observer_factory=runtime.observer,
                fault=runtime.fault,
                cleanup=runtime.cleanup,
            )
        },
        quality=QualityOwners(
            fresh_namespace=runtime.fresh_namespace,
            seed_audit=runtime.seed_audit,
            sources_factory=runtime.sources_factory,
            collectors_factory=runtime.collectors_factory,
            review_path=os.environ.get("ANALYTICS_BINDING_REVIEW_PATH"),
            schema_cache_path=os.environ.get("EVENT_SCHEMA_CACHE_PATH"),
            registry_url=os.environ.get("SCHEMA_REGISTRY_URL"),
            bootstrap_servers=os.environ.get("KAFKA_BOOTSTRAP_SERVERS"),
            cleanup=runtime.cleanup,
        ),
    )
