"""Read-only desktop observability, scoped facts and explicitly bounded samples.

Only M1's own database is read directly. Other modules use their validated APIs.
No Docker socket, database credentials, raw messages or provider secrets reach the UI.
"""

import asyncio
import os
from collections import Counter
from datetime import UTC, datetime, timedelta
from math import ceil
from time import monotonic

import httpx

from .clients import DependencyUnavailable, RemoteError, TransportConfig
from .provider_contracts import ContractUnavailable, ContractViolation
from .shopping_metrics import snapshot as session_snapshot

FAILURES = (DependencyUnavailable, RemoteError, ContractUnavailable, ContractViolation)
RECEIPT_LIMIT = 200


def utc(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ContractViolation("Missing UTC timestamp")
    return parsed.astimezone(UTC)


def p95(values):
    ordered = sorted(values)
    return ordered[ceil(len(ordered) * 0.95) - 1] if ordered else None


async def collect(workflow, context, day):
    deadline = monotonic() + 7
    dates = {
        "namespace": context.namespace,
        "date_from": day.isoformat(),
        "date_to": (day + timedelta(days=1)).isoformat(),
    }
    jobs = {
        "pipeline": ("gold", {"table": "pipeline_minute", "params": dates}),
        "orders": ("gold", {"table": "order_fact", "params": dates}),
        "silver": (
            "active_manifest",
            {"dataset": "silver", "params": {"namespace": context.namespace}},
        ),
        "gold": (
            "active_manifest",
            {"dataset": "gold", "params": {"namespace": context.namespace}},
        ),
        "receipts": (
            "receipts",
            {"params": {"namespace": context.namespace, "limit": RECEIPT_LIMIT}},
        ),
        "facets": ("facets", {"params": {"namespace": context.namespace}}),
        "capabilities": ("capabilities", {}),
    }

    analytics_slots = asyncio.Semaphore(2)

    async def execute_read(name, arguments):
        try:
            return await workflow.gateway.call(name, context, deadline=deadline, **arguments)
        except (*FAILURES, ValueError):
            return None

    async def read(name, arguments):
        if name in {"gold", "active_manifest", "receipts"}:
            async with analytics_slots:
                return await execute_read(name, arguments)
        return await execute_read(name, arguments)

    async def health():
        urls = {
            label: workflow.gateway.configs[key].base_url
            for label, key in (
                ("Catalogue", "catalog"),
                ("Orders", "transactions"),
                ("Analytics", "analytics"),
            )
        }
        urls.update(
            Inventory=os.environ.get("INVENTORY_BASE_URL", "http://inventory:8004"),
            Payments=os.environ.get("PAYMENTS_BASE_URL", "http://payments:8005"),
        )
        # Test-mode transport is explicit and uses the same declared owner double.
        async with httpx.AsyncClient(
            transport=workflow.gateway.transport,
            timeout=2.0,
            follow_redirects=False,
            trust_env=False,
        ) as client:

            async def probe(label, url):
                started = monotonic()
                try:
                    TransportConfig(url)
                    response = await client.get(url.rstrip("/") + "/health/ready")
                    ready = response.status_code == 200 and response.json().get("status") == "ready"
                    return {
                        "name": label,
                        "status": "ready" if ready else "unavailable",
                        "response_ms": round((monotonic() - started) * 1000, 2),
                    }
                except (httpx.HTTPError, ValueError, AttributeError):
                    return {"name": label, "status": "unavailable", "response_ms": None}

            return await asyncio.gather(*(probe(label, url) for label, url in urls.items()))

    values = await asyncio.gather(*(read(*job) for job in jobs.values()), health())
    return {**dict(zip(jobs, values[:-1], strict=True)), "services": values[-1]}


def pipeline_summary(gold, namespace, day, now):
    counts, minutes, sources = Counter(), Counter(), Counter()
    for row in gold["rows"]:
        if (
            row.get("namespace") != namespace
            or type(row.get("unique_events")) is not int
            or row["unique_events"] < 0
            or not isinstance(row.get("event_type"), str)
            or not isinstance(row.get("source_service"), str)
        ):
            raise ContractViolation("Invalid pipeline aggregate")
        minute = utc(row["minute"])
        if minute.date() != day:
            raise ContractViolation("Pipeline day mismatch")
        counts[row["event_type"]] += row["unique_events"]
        minutes[minute.replace(second=0, microsecond=0)] += row["unique_events"]
        sources[row["source_service"]] += row["unique_events"]
    end = now.replace(second=0, microsecond=0)
    # Real empty minute buckets are zero only after a valid complete Gold query.
    series = [
        {
            "minute": (end - timedelta(minutes=i)).isoformat(),
            "events": minutes[end - timedelta(minutes=i)],
        }
        for i in reversed(range(60))
        if (end - timedelta(minutes=i)).date() == day
    ]
    return {
        "events": sum(counts.values()),
        "by_type": dict(counts),
        "by_service": dict(sources),
        "minutes": series,
        "generation": gold["generation"],
    }


def dataset_summary(manifest, dataset, namespace):
    if manifest["namespace"] != namespace or manifest["dataset"] != dataset:
        raise ContractViolation("Dataset namespace mismatch")
    positions = {}
    for part in manifest["source_ranges"]:
        key = (part["topic"], part["partition"])
        positions[key] = max(positions.get(key, 0), part["next_offset"])
    return {
        "dataset": dataset,
        "generation": manifest["generation"],
        "created_at": manifest["created_at"],
        "files": len(manifest["files"]),
        "rows": sum(f["row_count"] for f in manifest["files"]),
        "bytes": sum(f["byte_size"] for f in manifest["files"]),
        "partitions": len(positions),
        "transform_version": manifest["transform_version"],
        "positions": [
            {"topic": k[0], "partition": k[1], "next_offset": v}
            for k, v in sorted(positions.items())[:20]
        ],
    }


def receipt_summary(page, namespace):
    counts, latencies, recent = Counter(), [], []
    unique = {}
    for row in page["receipts"]:
        if row["namespace"] != namespace:
            raise ContractViolation("Receipt namespace mismatch")
        source = row["source"]
        key = (source["topic"], source["partition"], source["offset"])
        previous = unique.get(key)
        if previous is not None and any(
            previous[field] != row[field] for field in ("raw_sha256", "event_id")
        ):
            raise ContractViolation("Conflicting receipt source identity")
        # The API joins journal entries to the current receipt. Several entries
        # can therefore return the same logical source position and timings.
        unique[key] = row
    for row in unique.values():
        counts[row["disposition"]] += 1
        elapsed = None
        if row["timing_validity"] == "observed" and row["gold_visible_at"]:
            elapsed = (utc(row["gold_visible_at"]) - utc(row["ingested_at"])).total_seconds() * 1000
            if elapsed < 0:
                elapsed = None
            else:
                latencies.append(elapsed)
        recent.append(
            {
                "event_id": row["event_id"],
                "source": row["source"],
                "disposition": row["disposition"],
                "timing_validity": row["timing_validity"],
                "gold_visible": row["gold_visible_at"] is not None,
                "ingested_at": row["ingested_at"],
                "visibility_ms": elapsed,
            }
        )
    return {
        "count": len(recent),
        "journal_observations": len(page["receipts"]),
        "limit": RECEIPT_LIMIT,
        # The API cursor is a resume position even on the last nonempty page.
        "complete": len(page["receipts"]) < RECEIPT_LIMIT,
        "dispositions": dict(counts),
        "visibility_p95_ms": p95(latencies),
        "observed_timings": len(latencies),
        "rows": sorted(recent, key=lambda r: r["ingested_at"], reverse=True)[:8],
    }


def snapshot(state, workflow, session_id, context):
    # The first operation authorizes session ownership before external probes.
    session = session_snapshot(state, None, session_id, context, include_pipeline=False)
    now = datetime.now(UTC)
    day = now.date()
    with state.database.transaction() as tx:
        rows = tx.execute(
            "SELECT created_at,response,intent_diagnostic FROM turns WHERE namespace=%s "
            "AND session_id=%s AND user_id=%s ORDER BY created_at DESC LIMIT 60",
            (context.namespace, session_id, context.user_id),
        ).fetchall()
        totals = tx.execute(
            "SELECT count(*) AS total, count(*) FILTER (WHERE published_at IS NULL) AS pending "
            "FROM outbox WHERE namespace=%s",
            (context.namespace,),
        ).fetchone()
        sessions = tx.execute(
            "SELECT count(*) AS n FROM sessions WHERE namespace=%s", (context.namespace,)
        ).fetchone()["n"]
    turns = [
        {
            "at": r["created_at"].isoformat(),
            "outcome": r["response"]["outcome"],
            "total_ms": r["response"]["timings_ms"]["total"],
            "model_ms": r["response"]["timings_ms"]["llm"],
            "search_ms": r["response"]["timings_ms"]["search"],
        }
        for r in reversed(rows)
    ]
    result = {
        "namespace": context.namespace,
        "checked_at": now,
        "pipeline_date_utc": str(day),
        "session": session,
        "activity": {
            "turns": turns,
            "namespace_sessions": sessions,
            "outbox_total": totals["total"],
            "outbox_pending": totals["pending"],
        },
        "pipeline": None,
        "datasets": [],
        "catalogue": None,
        "receipt_sample": None,
        "orders": None,
        "services": [{"name": "Conversation", "status": "ready", "response_ms": None}],
        "unavailable": [],
    }
    if workflow is None:
        result["unavailable"] = ["External providers"]
        return result
    data = asyncio.run(collect(workflow, context, day))
    result["services"] += data["services"]

    def project(key, fn):
        try:
            if data[key] is None:
                raise ContractViolation("Unavailable provider")
            return fn(data[key])
        except (ContractViolation, ValueError, TypeError, KeyError):
            result["unavailable"].append(key)
            return None

    result["pipeline"] = project(
        "pipeline", lambda g: pipeline_summary(g, context.namespace, day, now)
    )
    for dataset in ("silver", "gold"):
        summary = project(
            dataset, lambda m, name=dataset: dataset_summary(m, name, context.namespace)
        )
        if summary is not None:
            result["datasets"].append(summary)
    result["receipt_sample"] = project("receipts", lambda p: receipt_summary(p, context.namespace))

    def orders(gold):
        counts, amount, identities = Counter(), 0, set()
        for row in gold["rows"]:
            if (
                row.get("namespace") != context.namespace
                or row.get("currency") != "INR"
                or not isinstance(row.get("order_status"), str)
                or type(row.get("total_amount_minor")) is not int
                or row["total_amount_minor"] < 0
                or row.get("order_id") in identities
            ):
                raise ContractViolation("Invalid order fact")
            identities.add(row["order_id"])
            counts[row["order_status"]] += 1
            if row["order_status"] == "CONFIRMED":
                amount += row["total_amount_minor"]
        return {
            "count": len(identities),
            "by_status": dict(counts),
            "confirmed_minor": amount,
            "generation": gold["generation"],
        }

    result["orders"] = project("orders", orders)

    def catalogue(facets):
        caps = data["capabilities"]
        return {
            "dataset_revision": facets["dataset_revision"],
            "categories": len(facets["roots"]),
            "brands": len(facets["brands"]),
            "colours": len(facets["colours"]),
            "materials": len(facets["materials"]),
            "coverage_by_category": facets["coverage_by_category"],
            "hybrid_ready": "hybrid_exact" in caps["search_modes"] if caps else None,
        }

    result["catalogue"] = project("facets", catalogue)
    if data["capabilities"] is None:
        result["unavailable"].append("capabilities")
    if result["pipeline"] is not None:
        p = result["pipeline"]
        session.update(
            pipeline_status="available",
            pipeline_events_today=p["events"],
            pipeline_events_by_type=p["by_type"],
            gold_generation=p["generation"],
        )
    return result
