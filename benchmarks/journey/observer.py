"""Desktop diagnostic harness. Read-only SQL audits; owner APIs for business results.

This is not an operational service adapter. SQL transactions explicitly prohibit
writes, have statement deadlines and use only the project's fixed bindings.
"""

import copy
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from benchmarks.failure_demo.runtime import ROOT
from shared.contracts.analytics import SourceReceipt

from .model import elapsed, latency_summary, merge_observations, now, safe_event

SERVICES = ("conversation", "catalog", "orders", "inventory", "payments")
EVENT_LIMIT = 1200


def wire(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: wire(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [wire(item) for item in value]
    return value


class Observer:
    def __init__(self, runtime, infrastructure, root=ROOT):
        self.runtime, self.infrastructure, self.root = runtime, infrastructure, Path(root)
        self.lock = threading.RLock()
        self.cached, self.cached_at = None, 0
        self.context = {
            "run_id": str(uuid4()),
            "user_id": "journey-observer",
            "correlation_id": str(uuid4()),
        }
        self.clock = {"status": "unavailable", "error_bound_ms": None, "observed_at": None}
        self.clock_at = 0

    def audit(self, service, read):
        url = self.runtime.values[service.upper() + "_DATABASE_URL"]
        with psycopg.connect(
            url,
            row_factory=dict_row,
            connect_timeout=2,
            options="-ctimezone=UTC -cstatement_timeout=2500",
        ) as tx:
            tx.execute("SET TRANSACTION READ ONLY")
            return read(tx)

    def outbox(self, service, identity=None):
        def read(tx):
            totals = tx.execute(
                "SELECT count(*) FILTER (WHERE published_at IS NULL) AS pending, "
                "min(produced_at) FILTER (WHERE published_at IS NULL) AS oldest_at "
                "FROM outbox WHERE namespace=%s",
                (self.runtime.namespace,),
            ).fetchone()
            where, params = "namespace=%s", [self.runtime.namespace]
            if identity:
                where += (
                    " AND (event_id::text=%s OR aggregate_id=%s OR "
                    "convert_from(payload,'UTF8')::jsonb->'payload'->>'order_id'=%s OR "
                    "convert_from(payload,'UTF8')::jsonb->'payload'->>'search_id'=%s OR "
                    "convert_from(payload,'UTF8')::jsonb->'payload'->>'turn_id'=%s)"
                )
                params.extend([identity] * 5)
            rows = tx.execute(
                "SELECT payload,published_at FROM outbox WHERE "
                + where
                + " ORDER BY outbox_id DESC LIMIT 180",
                params,
            ).fetchall()
            events = []
            for row in rows:
                try:
                    doc = json.loads(bytes(row["payload"]))
                    if "event_type" not in doc or doc.get("namespace") != self.runtime.namespace:
                        continue
                    events.append(
                        {
                            **safe_event(doc),
                            "outbox_pending": row["published_at"] is None,
                            "outbox_marked_published_at": wire(row["published_at"]),
                        }
                    )
                except (ValueError, TypeError):
                    continue
            age = elapsed(wire(totals["oldest_at"]), now())
            return {
                "service": service,
                "pending": totals["pending"],
                "oldest_pending_age_seconds": age / 1000 if age is not None else None,
                "oldest_at": wire(totals["oldest_at"]),
                "status": "observed",
                "observed_at": now(),
                "events": events,
            }

        return self.audit(service, read)

    def analytical_audit(self, identity=None):
        def read(tx):
            where, params = "s.namespace=%s", [self.runtime.namespace]
            if identity:
                where += (
                    " AND (s.event_id::text=%s OR e.aggregate_id=%s OR "
                    "e.document->'payload'->>'order_id'=%s OR "
                    "e.document->'payload'->>'search_id'=%s OR "
                    "e.document->'payload'->>'turn_id'=%s)"
                )
                params.extend([identity] * 5)
            rows = tx.execute(
                "SELECT s.*,e.document FROM source_receipts s LEFT JOIN silver_events e "
                "ON e.namespace=s.namespace AND e.event_id=s.event_id "
                "AND s.disposition IN ('new_valid','duplicate_delivery','redelivery_noop') "
                "WHERE " + where + " ORDER BY s.ingested_at DESC LIMIT %s",
                [*params, EVENT_LIMIT + 1],
            ).fetchall()
            receipts, documents = [], []
            for row in rows[:EVENT_LIMIT]:
                if row["disposition"] is None:
                    continue
                fields = (
                    "raw_sha256",
                    "disposition",
                    "reason_code",
                    "ingested_at",
                    "bronze_durable_at",
                    "silver_committed_observed_at",
                    "gold_visible_at",
                    "visibility_generation",
                    "timing_validity",
                )
                receipt = SourceReceipt.model_validate(
                    {
                        "namespace": self.runtime.namespace,
                        "source": {
                            "topic": row["topic"],
                            "partition": row["partition"],
                            "offset": row["offset_number"],
                            "raw_locator": row["raw_locator"],
                        },
                        "event_id": str(row["event_id"]) if row["event_id"] else None,
                        **{key: row[key] for key in fields},
                    }
                ).model_dump(mode="json")
                receipts.append(receipt)
                if row["document"]:
                    documents.append(
                        {
                            **safe_event(row["document"]),
                            "source": receipt["source"],
                            "raw_sha256": receipt["raw_sha256"],
                            "kafka_observed_at": receipt["ingested_at"],
                            "kafka_observation_basis": "consumer capture ingested_at",
                        }
                    )
            pending = tx.execute(
                "SELECT count(*) AS pending,min(s.silver_committed_observed_at) AS oldest_at "
                "FROM export_pending p JOIN silver_events e USING(namespace,event_id) "
                "JOIN source_receipts s ON s.namespace=e.namespace AND s.topic=e.source_topic "
                "AND s.partition=e.source_partition AND s.offset_number=e.source_offset "
                "WHERE p.namespace=%s",
                (self.runtime.namespace,),
            ).fetchone()
            age = elapsed(wire(pending["oldest_at"]), now())
            return {
                "receipts": receipts,
                "documents": documents,
                "bounded": len(rows) > EVENT_LIMIT,
                "pending": {
                    "count": pending["pending"],
                    "oldest_at": wire(pending["oldest_at"]),
                    "oldest_age_seconds": age / 1000 if age is not None else None,
                    "age_basis": "since Silver commit observation; upper bound",
                    "status": "observed",
                    "observed_at": now(),
                },
            }

        return self.audit("analytics", read)

    def catalogue(self):
        # Pinned project import artifacts; no arbitrary path from the browser.
        candidates = [
            self.root / "artifacts/prototype-setup/prototype-data",
            self.root / "artifacts/infra/prototype-local",
            self.root / "artifacts/prototype-setup",
            self.root / "artifacts/infra/catalog-local",
        ]
        result = {"status": "unavailable", "source": None, "normalization": None, "timings": None}

        def read(tx):
            imported = tx.execute(
                "SELECT import_id::text,source_hash,rules_version,dictionary_sha256,"
                "dataset_revision,canonical_rows,status,started_at,completed_at "
                "FROM catalog_imports WHERE namespace=%s ORDER BY started_at DESC LIMIT 1",
                (self.runtime.namespace,),
            ).fetchone()
            if not imported:
                return None
            dispositions = tx.execute(
                "SELECT disposition,count(*) AS n FROM source_dispositions "
                "WHERE namespace=%s AND source_hash=%s GROUP BY disposition",
                (self.runtime.namespace, imported["source_hash"]),
            ).fetchall()
            return imported, {r["disposition"]: r["n"] for r in dispositions}

        audited = self.audit("catalog", read)
        if audited:
            imported, dispositions = audited
            # Never mix an unrelated desktop import's archive or timings into
            # the namespace selected in the browser.
            for folder in candidates:
                source_path = folder / "source_manifest.json"
                try:
                    if not source_path.is_file() or source_path.stat().st_size >= 2_000_000:
                        continue
                    source = json.loads(source_path.read_text("utf-8"))
                    if (
                        source.get("source_sha256") != imported["source_hash"]
                        or source.get("dataset_revision") != imported["dataset_revision"]
                    ):
                        continue
                    result["source"] = {
                        k: source.get(k)
                        for k in ("acquired_at", "dataset_revision", "raw_archive_descriptor")
                    }
                    timing = folder / "import_timings.json"
                    # Timings belong to an import execution, not just a dataset.
                    if timing.is_file() and timing.stat().st_size < 2_000_000:
                        measured = json.loads(timing.read_text("utf-8"))
                        if str(measured.get("import_id")) == imported["import_id"]:
                            result["timings"] = measured
                    break
                except (OSError, ValueError):
                    continue
            result["normalization"] = {
                **wire(imported),
                "canonical_rows": imported["canonical_rows"],
                "active_rows": dispositions.get("canonical_active"),
                "disposition_counts": dispositions,
            }
            result["source"] = {
                **(result["source"] or {}),
                "source_sha256": imported["source_hash"],
                "row_count": sum(dispositions.values()),
                "import_started_at": wire(imported["started_at"]),
                "rules_version": imported["rules_version"],
            }
            # Resolve and hash only the archive selected by the audited source hash.
            try:
                import re

                source_hash = imported["source_hash"]
                if not re.fullmatch(r"[a-f0-9]{64}", source_hash):
                    raise ValueError("Invalid recorded source hash")
                script = (
                    "import pathlib,hashlib,json,sys; r=pathlib.Path('/lakehouse'); "
                    "p=list((r/'raw/catalog'/sys.argv[1]).glob('*.csv')); "
                    "print(json.dumps([{'path':str(f.relative_to(r)),"
                    "'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),"
                    "'byte_size':f.stat().st_size} for f in p if f.is_file()]))"
                )
                target = self.runtime.container("analytics-worker")
                found = json.loads(
                    self.runtime.docker("exec", target["Id"], "python", "-c", script, source_hash)
                )
                matching = next((f for f in found if f["sha256"] == source_hash), None)
                result["source"]["raw_archive_descriptor"] = matching
                result["source"]["archive_verified"] = matching is not None
            except Exception:
                result["source"]["archive_verified"] = None
        if result["source"] or result["normalization"]:
            result["status"] = "recorded_import_evidence"
        return result

    def clock_check(self):
        if time.monotonic() - self.clock_at < 60:
            return self.clock
        try:
            target = self.runtime.container("analytics-worker")
            start_wall, start = time.time(), time.monotonic()
            remote = float(
                self.runtime.docker(
                    "exec", target["Id"], "python", "-c", "import time; print(time.time())"
                )
            )
            duration = time.monotonic() - start
            drift = abs((time.time() - start_wall) - duration)
            offset = remote - (start_wall + duration / 2)
            bound = (abs(offset) + duration / 2) * 1000
            self.clock = {
                "status": "qualified" if drift < 0.05 and bound <= 1000 else "unqualified",
                "error_bound_ms": round(bound, 2),
                "offset_estimate_ms": round(offset * 1000, 2),
                "round_trip_ms": round(duration * 1000, 2),
                "observed_at": now(),
                "basis": "Windows host / shared Docker VM clock; round-trip bound; 1000 ms gate",
            }
        except Exception:
            self.clock = {
                "status": "unavailable",
                "error_bound_ms": None,
                "observed_at": now(),
                "basis": "Clock probe unavailable; cross-service quantiles withheld",
            }
        self.clock_at = time.monotonic()
        return self.clock

    def snapshot(self, identity=None):
        with self.lock:
            if not identity and self.cached and time.monotonic() - self.cached_at < 4:
                return copy.deepcopy(self.cached)
            checked = now()
            unavailable, producers, outboxes = [], [], []

            def attempt(name, read):
                try:
                    return read()
                except Exception:
                    return None

            jobs = {role: lambda r=role: self.outbox(r, identity) for role in SERVICES}
            jobs["analytics_audit"] = lambda: self.analytical_audit(identity)
            jobs["infrastructure"] = self.infrastructure.snapshot
            jobs["clock"] = self.clock_check
            jobs["catalogue"] = self.catalogue
            for dataset in ("silver", "gold"):
                jobs[dataset] = lambda d=dataset: self.runtime.call(
                    "analytics",
                    "GET",
                    f"/v1/analytics/manifests/{d}/active",
                    self.context,
                    params={"namespace": self.runtime.namespace},
                )
            jobs["projection"] = lambda: self.runtime.call(
                "catalog",
                "GET",
                "/internal/v1/projection/receipts",
                self.context,
                params={"limit": 1000},
            )
            with ThreadPoolExecutor(max_workers=5) as pool:
                future = {key: pool.submit(attempt, key, read) for key, read in jobs.items()}
                data = {key: value.result() for key, value in future.items()}
            for role in SERVICES:
                row = data[role]
                if row is None:
                    row = {
                        "service": role,
                        "pending": None,
                        "oldest_pending_age_seconds": None,
                        "oldest_at": None,
                        "status": "unavailable",
                        "observed_at": checked,
                    }
                else:
                    producers.extend(row.pop("events"))
                outboxes.append(row)
            analytical = data["analytics_audit"] or {}
            events = merge_observations(
                producers, analytical.get("receipts", []), analytical.get("documents", [])
            )
            projection = {r["event_id"]: r for r in (data["projection"] or {}).get("receipts", [])}
            for event in events:
                event["projection"] = projection.get(event.get("event_id"))
            clock = data["clock"] or {"status": "unavailable", "error_bound_ms": None}
            result = {
                "schema": "journey-snapshot-v1",
                "namespace": self.runtime.namespace,
                "observed_at": checked,
                "mode": "live",
                "clock": clock,
                "events": events[:1500],
                "outboxes": outboxes,
                "pending_gold": analytical.get("pending")
                or {"count": None, "oldest_age_seconds": None, "status": "unavailable"},
                "manifests": {k: data[k] for k in ("silver", "gold")},
                "catalogue": data["catalogue"],
                "infrastructure": data["infrastructure"],
                "latency": latency_summary(events, clock),
                "rates": {
                    "offered_per_second": None,
                    "admitted_per_second": None,
                    "gold_goodput_per_second": None,
                    "status": "no_generated_workload",
                    "basis": (
                        "No active generated workload; interactive traffic has no intended schedule"
                    ),
                },
                "bounds": {
                    "source_limit": EVENT_LIMIT,
                    "outbox_per_service": 180,
                    "source_truncated": analytical.get("bounded", False),
                    "projection_limit": 1000,
                    "scope": (
                        "Recent bounded namespace observations; enter an ID for a targeted audit"
                    ),
                },
                "unavailable": unavailable,
            }
            unavailable.extend(key for key, value in data.items() if value is None)
            if not identity:
                self.cached, self.cached_at = copy.deepcopy(result), time.monotonic()
            return result

    def trace(self, kind, identity):
        from .model import related_events, timeline

        data = self.snapshot(identity)
        if kind == "event":
            seed = next((e for e in data["events"] if e.get("event_id") == identity), None)
            payload = (seed or {}).get("payload", {})
            business_id = next(
                (payload.get(k) for k in ("order_id", "search_id", "turn_id") if payload.get(k)),
                None,
            )
            if business_id and business_id != identity:
                expanded = self.snapshot(business_id)
                expanded["events"] = list(
                    {e["key"]: e for e in [*data["events"], *expanded["events"]]}.values()
                )
                data = expanded
        events = related_events(data["events"], kind, identity)
        ids = sorted({e["event_id"] for e in events if e.get("event_id")})
        visibility = None
        business = None
        if ids:
            # The owner endpoint accepts at most 100 IDs. Resolve bounded chunks,
            # and combine them only when they pin the same queryable generation.
            selected = ids[:1000]

            def visible(chunk):
                return self.runtime.call(
                    "analytics",
                    "POST",
                    "/internal/v1/analytics/visibility",
                    self.context,
                    body={"namespace": self.runtime.namespace, "event_ids": chunk},
                    optional=True,
                )

            with ThreadPoolExecutor(max_workers=3) as pool:
                parts = list(
                    pool.map(visible, [selected[i : i + 100] for i in range(0, len(selected), 100)])
                )
            if (
                all(p and p.get("queryable") for p in parts)
                and len({(p["generation"], p.get("manifest_sha256")) for p in parts}) == 1
            ):
                visibility = {
                    **parts[0],
                    "checked_event_ids": selected,
                    "visible_event_ids": sorted({v for p in parts for v in p["visible_event_ids"]}),
                    "missing_event_ids": sorted({v for p in parts for v in p["missing_event_ids"]}),
                }
            else:
                data["unavailable"].append("exact_active_gold_membership")
            data["bounds"].update(visibility_limit=1000, visibility_truncated=len(ids) > 1000)
        order = next((e for e in events if e.get("payload", {}).get("order_id")), None)
        if order:
            day = (order["payload"].get("created_at") or order.get("event_time") or now())[:10]
            end = (datetime.fromisoformat(day) + timedelta(days=1)).date().isoformat()
            facts = self.runtime.call(
                "analytics",
                "GET",
                "/v1/analytics/gold/order_fact",
                self.context,
                params={"namespace": self.runtime.namespace, "date_from": day, "date_to": end},
                optional=True,
            )
            if facts:
                business = {
                    "generation": facts["generation"],
                    "table": "order_fact",
                    "rows": [
                        r
                        for r in facts["rows"]
                        if r.get("order_id") == order["payload"]["order_id"]
                    ],
                }
        elif events:
            event = events[0]
            day = (event.get("event_time") or now())[:10]
            end = (datetime.fromisoformat(day) + timedelta(days=1)).date().isoformat()
            table = "search_performance" if kind == "search" else "pipeline_minute"
            facts = self.runtime.call(
                "analytics",
                "GET",
                "/v1/analytics/gold/" + table,
                self.context,
                params={"namespace": self.runtime.namespace, "date_from": day, "date_to": end},
                optional=True,
            )
            if facts:
                business = {
                    "generation": facts["generation"],
                    "table": table,
                    "rows": facts["rows"][:40],
                    "scope": "Aggregate result; exact event membership is reported separately",
                }
        return {
            "kind": kind,
            "id": identity,
            "namespace": data["namespace"],
            "observed_at": data["observed_at"],
            "events": events,
            "status": "observed" if events else "not_found_or_unavailable",
            "clock": data["clock"],
            "visibility": visibility,
            "business_result": business,
            "timelines": {e["key"]: timeline(e, data["clock"]) for e in events},
            "unavailable": data["unavailable"],
            "bounds": data["bounds"],
        }
