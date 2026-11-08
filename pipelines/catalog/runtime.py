"""Catalogue owner bindings for projectctl.team_runtime.

Select with PROJECTCTL_OWNER_RUNTIME_MODULES=pipelines.catalog.runtime. Registering opens no
connection and starts nothing. Checks read through SELECT-only roles: CATALOG_AUDIT_DATABASE_URL,
and INVENTORY_AUDIT_DATABASE_URL for the seed proof (Vichitr's audit roles). Other deployment
inputs: CATALOG_METRICS_URL, CATALOG_BINDING_REVIEW_PATH, PROJECTCTL_SUT_CONTAINERS and, for
W-ANALYTICS, ANALYTICS_FROZEN_LAYOUTS (from `python -m analytics.queries.layouts freeze`).
"""

import asyncio
import json
import os
import re
import shutil
from collections import defaultdict
from pathlib import Path
from time import monotonic

import psycopg
import pyarrow as pa
import pyarrow.parquet as pq
from psycopg import sql

from benchmarks.composition import OwnerCallbacks
from pipelines.catalog import search_oracle
from pipelines.catalog.adapter import database_url, seed_facts
from projectctl.artifacts import file_hash, write_json
from projectctl.models import ExitCode
from projectctl.providers import DependencyError, ProviderResult
from projectctl.runtime import RuntimeBindings
from projectctl.setup import ResetParticipant

ROOT = Path(__file__).resolve().parents[2]
SEARCH_EXPECTATIONS = ROOT / "contracts/fixtures/catalog/search_expectations.json"
# quote_lines references quotes; chunks, stage and products reference catalog_imports.
RESET_FIRST, RESET_LAST = ("quote_lines",), ("catalog_stage", "catalog_import_chunks")


def read_connection(variable):
    from infra.analytics_runtime import read_connection as select_only

    return select_only(variable)


def namespace_tables(tx):
    return [
        row[0]
        for row in tx.execute(
            "SELECT table_name FROM information_schema.columns WHERE "
            "table_schema = current_schema() AND column_name = 'namespace' ORDER BY 1"
        ).fetchall()
    ]


def namespace_rows(tx, namespace):
    """Rows per catalogue table for one namespace; a not-yet-migrated database has none."""
    return {
        table: tx.execute(
            sql.SQL("SELECT count(*) FROM {} WHERE namespace = %s").format(sql.Identifier(table)),
            (namespace,),
        ).fetchone()[0]
        for table in namespace_tables(tx)
    }


def pending_outbox(tx, namespace):
    if "outbox" not in namespace_tables(tx):
        return 0
    return tx.execute(
        "SELECT count(*) FROM outbox WHERE namespace = %s AND published_at IS NULL", (namespace,)
    ).fetchone()[0]


def inventory_facts(tx, namespace):
    """Read-only Inventory proof for the seed: its SKU set, pending outbox and seed run ID."""
    skus = {
        row[0] for row in tx.execute("SELECT sku FROM inventory WHERE namespace = %s", (namespace,))
    }
    pending = pending_outbox(tx, namespace)
    runs = tx.execute(
        "SELECT DISTINCT convert_from(payload, 'UTF8')::jsonb->>'run_id' FROM outbox "
        "WHERE namespace = %s",
        (namespace,),
    ).fetchall()
    return skus, pending, [row[0] for row in runs]


def require_bench(namespace):
    """The runner's own rule for an isolated benchmark namespace."""
    if not re.fullmatch(r"bench-[a-z0-9][a-z0-9-]{0,55}", namespace) or re.match(
        r"bench-(dev|live|prod|production)(-|$)", namespace
    ):
        raise DependencyError("catalogue checks run only in an isolated bench- namespace")


class CatalogRuntime:
    def __init__(self, read=read_connection, write_url=database_url):
        self.read, self.write_url = read, write_url

    def run(self, function, *arguments):
        return asyncio.to_thread(function, *arguments)

    # Lifecycle

    def _fresh(self, context, databases):
        require_bench(context["namespace"])
        rows = {}
        for name in databases:
            with self.read(name.upper() + "_AUDIT_DATABASE_URL") as tx:
                rows[name] = namespace_rows(tx, context["namespace"])
        used = {
            f"{db}.{table}": n for db, tables in rows.items() for table, n in tables.items() if n
        }
        if used:
            raise DependencyError("namespace is not fresh: " + json.dumps(used, sort_keys=True))
        return {
            "namespace": context["namespace"],
            "run_id": context["run_id"],
            "created_new": True,
            "rows_before": rows,
        }

    async def fresh_catalog(self, context):
        return await self.run(self._fresh, context, ("catalog",))

    async def fresh_catalog_inventory(self, context):
        return await self.run(self._fresh, context, ("catalog", "inventory"))

    async def fresh_analytics(self, context):
        return await self.run(self._fresh, context, ("analytics",))

    def _seed(self, context):
        namespace = context["namespace"]
        with self.read("CATALOG_AUDIT_DATABASE_URL") as tx:
            facts = seed_facts(tx, namespace)
            active = {
                row[0]
                for row in tx.execute(
                    "SELECT sku FROM products WHERE namespace = %s AND active", (namespace,)
                )
            }
        with self.read("INVENTORY_AUDIT_DATABASE_URL") as tx:
            stocked, pending, runs = inventory_facts(tx, namespace)
        if stocked != active:
            raise DependencyError(
                f"Inventory holds {len(stocked)} SKUs, {len(stocked ^ active)} differing from the "
                f"{len(active)} active catalogue SKUs"
            )
        if len(runs) != 1 or not runs[0]:
            raise DependencyError("Inventory seed outbox lacks exactly one run ID")
        return facts | {"run_id": runs[0], "pending_outbox": pending}

    async def seed_audit(self, context):
        return await self.run(self._seed, context)

    def _pending(self, namespace):
        with self.read("CATALOG_AUDIT_DATABASE_URL") as tx:
            return pending_outbox(tx, namespace)

    async def drain(self, context, remaining_seconds):
        """Search and price events must leave the catalogue outbox through the relay."""
        deadline = monotonic() + max(remaining_seconds - 1, 0)
        while (pending := await self.run(self._pending, context["namespace"])) != 0:
            if monotonic() >= deadline:
                raise DependencyError(f"catalogue outbox still holds {pending} unpublished rows")
            await asyncio.sleep(0.25)

    # Reset participant: preflight reads, apply deletes one bench namespace in one transaction.

    def reset_preflight(self, invocation):
        require_bench(invocation.namespace)
        with self.read("CATALOG_AUDIT_DATABASE_URL") as tx:
            rows, pending = (
                namespace_rows(tx, invocation.namespace),
                pending_outbox(tx, invocation.namespace),
            )
        if pending:
            return ProviderResult(
                ExitCode.DEPENDENCY_FAILURE,
                (f"catalogue outbox holds {pending} unpublished rows; drain before reset",),
                "real",
            )
        return ProviderResult(
            ExitCode.COMPLETED,
            ("catalogue rows to delete: " + json.dumps(rows, sort_keys=True),),
            "real",
        )

    def reset_apply(self, invocation):
        namespace = invocation.namespace
        require_bench(namespace)
        with psycopg.connect(self.write_url(), connect_timeout=5) as tx:
            if pending_outbox(tx, namespace):
                return ProviderResult(
                    ExitCode.DEPENDENCY_FAILURE,
                    ("catalogue outbox changed since preflight",),
                    "real",
                )
            imports = sql.SQL(
                "import_id IN (SELECT import_id FROM catalog_imports WHERE namespace = %s)"
            )
            tables = namespace_tables(tx)
            ordered = [t for t in RESET_FIRST if t in tables] + [
                t for t in tables if t not in RESET_FIRST and t != "catalog_imports"
            ]
            deleted = {}
            for table in ordered:
                deleted[table] = tx.execute(
                    sql.SQL("DELETE FROM {} WHERE namespace = %s").format(sql.Identifier(table)),
                    (namespace,),
                ).rowcount
            for table in RESET_LAST:
                deleted[table] = tx.execute(
                    sql.SQL("DELETE FROM {} WHERE ").format(sql.Identifier(table)) + imports,
                    (namespace,),
                ).rowcount
            if "catalog_imports" in tables:
                deleted["catalog_imports"] = tx.execute(
                    "DELETE FROM catalog_imports WHERE namespace = %s", (namespace,)
                ).rowcount
        return ProviderResult(
            ExitCode.COMPLETED,
            ("catalogue rows deleted: " + json.dumps(deleted, sort_keys=True),),
            "real",
        )

    # W-SEARCH audit

    def _search_audit(self, context, directory):
        directory = Path(directory)
        namespace = context["namespace"]
        frozen = json.loads(SEARCH_EXPECTATIONS.read_text(encoding="utf-8"))
        queries = {
            q["query_id"]: q["request"]
            for q in json.loads(search_oracle.QUERIES.read_text(encoding="utf-8"))["queries"]
        }
        if file_hash(search_oracle.QUERIES) != frozen["queries_sha256"]:
            raise DependencyError("frozen search expectations were made for different queries")
        rows = [json.loads(line) for line in (directory / "emissions.jsonl").open(encoding="utf-8")]
        by_query, unresolved = defaultdict(list), 0
        for row in rows:
            unresolved += row["outcome"] == "unresolved"
            by_query[row["payload"]["query_id"]].append(row)
        skus = sorted(
            {
                hit["sku"]
                for row in rows
                if row["outcome"] == "acknowledged"
                for hit in row["details"]["search"]["hits"]
            }
        )
        with self.read("CATALOG_AUDIT_DATABASE_URL") as tx:
            facts = {
                row[0]: dict(zip(search_oracle.COLUMNS, row[:-1], strict=True))
                | {"available": row[-1]}
                for row in tx.execute(
                    "SELECT p.sku, p.active, p.category, p.category_path, p.brand_normalized, "
                    "p.size, p.colour, p.material, p.price_minor, p.dataset_revision, s.available "
                    "FROM products p LEFT JOIN stock_projection s "
                    "ON s.namespace = p.namespace AND s.sku = p.sku "
                    "WHERE p.namespace = %s AND p.sku = ANY(%s)",
                    (namespace, skus),
                ).fetchall()
            }
            revision = tx.execute(
                "SELECT DISTINCT dataset_revision FROM products WHERE namespace = %s AND active",
                (namespace,),
            ).fetchall()
            # Plans are taken after the measured window, on the same data and indexes.
            from pipelines.catalog.experiments import explain

            mode = context.get("parameters", {}).get("retrieval_mode", "lexical")
            for spec in json.loads(search_oracle.QUERIES.read_text(encoding="utf-8"))["queries"]:
                explain(
                    tx, spec, namespace, mode, directory / "plans", context.get("variant_id", "run")
                )
        if len(revision) != 1:
            raise DependencyError("search namespace lacks exactly one active dataset revision")
        revision = revision[0][0]
        observed, table = {}, []
        for query_id, request in queries.items():
            receipts = by_query.get(query_id, [])
            accepted = [r["details"]["search"] for r in receipts if r["outcome"] == "acknowledged"]
            if not receipts:
                continue
            if not accepted:
                observed[query_id] = {"status": "rejected"}
                continue
            if len(accepted) != len(receipts):
                observed[query_id] = {"status": "mixed"}
                continue
            violations = 0
            for response in accepted:
                hits = response["hits"]
                violations += not (
                    response["candidate_count"]
                    >= response["eligible_count"]
                    >= response["returned_count"]
                    == len(hits)
                    <= request["top_k"]
                )
                for hit in hits:
                    row = facts.get(hit["sku"])
                    violations += not (
                        row
                        and row["active"]
                        and (row["available"] or 0) > 0
                        and row["dataset_revision"] == revision == hit["dataset_revision"]
                        and search_oracle.satisfies(row, request["intent"])
                    )
                table.append(
                    {
                        "query_id": query_id,
                        "eligible_count": response["eligible_count"],
                        "returned_count": response["returned_count"],
                        "skus": [hit["sku"] for hit in hits],
                    }
                )
            counts = {r["eligible_count"] for r in accepted}
            observed[query_id] = {
                "status": "ok",
                "eligible_count": counts.pop() if len(counts) == 1 else None,
                "hard_filter_violations": violations,
                "deterministic_hits": len({tuple(h["sku"] for h in r["hits"]) for r in accepted})
                == 1,
            }
        expected = {
            query_id: {"status": "rejected"} if value["status"] == "rejected" else value
            for query_id, value in frozen["logical_results"].items()
        }
        return self._finish(
            context,
            directory,
            "W-SEARCH",
            SEARCH_EXPECTATIONS,
            expected,
            observed,
            complete=set(observed) == set(expected) and unresolved == 0,
            table=table,
            manifests={"search_expectations": frozen, "dataset_revision": revision},
        )

    async def search_audit(self, context, directory):
        return await self.run(self._search_audit, context, directory)

    def _finish(
        self, context, directory, kind, fixture, expected, observed, *, complete, table, manifests
    ):
        """Raw evidence the P9 validator reads, then the verdict. Nothing is written to the SUT."""
        from benchmarks.integration import validate_review
        from benchmarks.reconciliation import compare_fixture_output

        namespace = context["namespace"]
        shutil.copyfile(fixture, directory / "source_fixture.json")
        review = os.environ.get("CATALOG_BINDING_REVIEW_PATH")
        reviewed = None
        if review:
            shutil.copyfile(review, directory / "binding_review.json")
            reviewed = validate_review(
                directory / "binding_review.json", namespace, directory / "source_fixture.json"
            )
        write_json(
            directory / "expected.json",
            {
                "namespace": namespace,
                "audit_kind": kind,
                "source_fixture_sha256": file_hash(fixture),
                "logical_results": expected,
            },
        )
        write_json(
            directory / "observed.json",
            {
                "namespace": namespace,
                "test_mode": "real",
                "collection_complete": complete,
                "logical_results": observed,
            },
        )
        pq.write_table(
            pa.Table.from_pylist(table)
            if table
            else pa.table({"query_id": pa.array([], pa.string())}),
            directory / "query_results.parquet",
            compression="zstd",
        )
        (directory / "manifests").mkdir(exist_ok=True)
        write_json(directory / "manifests" / f"{kind.lower()}_inputs.json", manifests)
        comparison = compare_fixture_output(expected, observed)
        return {
            "passed": comparison["passed"] if complete else None,
            "test_mode": "real",
            "namespace": namespace,
            "audit_kind": kind,
            "collection_complete": complete,
            "mismatched_paths": comparison["mismatched_paths"],
            "binding_review": reviewed,
            "scope": "independent expectations frozen before the run; receipts and read-only SQL",
        }

    # W-ANALYTICS

    def _analytics_audit(self, context, directory):
        from analytics.queries.layouts import load_frozen, verify_files

        directory = Path(directory)
        path = Path(os.environ["ANALYTICS_FROZEN_LAYOUTS"])
        frozen = load_frozen(path)
        name = frozen.layout_name(context["parameters"])
        changed = verify_files(frozen, name)
        rows = [json.loads(line) for line in (directory / "emissions.jsonl").open(encoding="utf-8")]
        digests, table, unresolved = defaultdict(set), [], 0
        for row in rows:
            unresolved += row["outcome"] == "unresolved"
            if row["outcome"] == "acknowledged":
                details = row["details"]
                digests[row["payload"]["query_id"]].add(details["result_digest"])
                table.append({"query_id": row["payload"]["query_id"]} | details)
        observed = {
            query_id: {"result_digest": values.pop() if len(values) == 1 else None}
            for query_id, values in digests.items()
        }
        expected = {q: {"result_digest": d} for q, d in frozen.document["expected_digests"].items()}
        return self._finish(
            context,
            directory,
            "W-ANALYTICS",
            path,
            expected,
            observed,
            complete=set(observed) == set(expected) and unresolved == 0 and not changed,
            table=table,
            manifests={"layout": name, "changed_files": changed} | frozen.summary(),
        )

    async def analytics_audit(self, context, directory):
        return await self.run(self._analytics_audit, context, directory)

    def analytics_inputs(self):
        """layout_for and query_day from the frozen file, or both missing so the runner refuses."""
        path = os.environ.get("ANALYTICS_FROZEN_LAYOUTS")
        if not path:
            return None, None
        from analytics.queries.layouts import load_frozen

        frozen = load_frozen(Path(path))
        return frozen.layout_for, frozen.query_day

    # Observation

    def observer(self, context, directory, kind):
        from benchmarks.collectors import Series
        from benchmarks.runtime_observer import MetricsTarget, RuntimeObserver

        url = os.environ.get("CATALOG_METRICS_URL")
        if not url:
            raise DependencyError("CATALOG_METRICS_URL required for the catalogue SUT target")
        target = MetricsTarget(
            "catalog",
            url,
            (
                Series("process_cpu_seconds_total", "catalog", "seconds", ()),
                Series("process_resident_memory_bytes", "catalog", "bytes", ()),
            ),
        )
        return RuntimeObserver((target,), resource_factory=sut_resources)(context, directory, kind)


def sut_resources(context):
    """One Docker collector per declared container of every profile service, none guessed."""
    from benchmarks.collectors import collector
    from infra.analytics_resources import DockerResources

    targets = json.loads(os.environ.get("PROJECTCTL_SUT_CONTAINERS", "{}"))
    services = context["resource_profile"]["services"]
    missing = [name for name in services if not targets.get(name)]
    if missing:
        raise DependencyError("PROJECTCTL_SUT_CONTAINERS lacks: " + ", ".join(missing))
    readers = []
    for name in services:
        containers = targets[name] if isinstance(targets[name], list) else [targets[name]]
        for index, container in enumerate(containers):
            label = name if len(containers) == 1 else f"{name}-{index}"
            readers.append(
                collector("resources-" + label, DockerResources(container, label, service=name))
            )
    return tuple(readers)


def runtime_bindings():
    runtime = CatalogRuntime()
    layout_for, query_day = runtime.analytics_inputs()
    return RuntimeBindings(
        workloads={
            "W-IMPORT": OwnerCallbacks(fresh_namespace=runtime.fresh_catalog),
            "W-SEARCH": OwnerCallbacks(
                fresh_namespace=runtime.fresh_catalog_inventory,
                seed_audit=runtime.seed_audit,
                drain=runtime.drain,
                audit=runtime.search_audit,
                observer_factory=runtime.observer,
            ),
            "W-ANALYTICS": OwnerCallbacks(
                fresh_namespace=runtime.fresh_analytics,
                drain=lambda context, remaining_seconds: asyncio.sleep(0),
                audit=runtime.analytics_audit,
                observer_factory=runtime.observer,
                layout_for=layout_for,
                query_day=query_day,
            ),
        },
        resets={"catalog": ResetParticipant(runtime.reset_preflight, runtime.reset_apply)},
    )
