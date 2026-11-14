"""Real HTTP -> outbox -> Kafka -> active Gold comparisons on the Desktop prototype.

Sequential finite integration trials, not the formal sustained-rate P9 campaign.
No service SQL reads/writes, no fabricated events and no approval receipts generated.
"""

import argparse
import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from confluent_kafka import Consumer, TopicPartition

from benchmarks.failure_demo.controller import Controller, Selection
from benchmarks.failure_demo.runtime import Runtime
from benchmarks.windows.evidence import ROOT, desktop_only, digest, live_snapshot, write
from benchmarks.windows.infrastructure import Infrastructure
from benchmarks.windows.measure import compare, paired
from infra import postgres, prototype, retrieval, streaming


def set_batch(rows, directory):
    """Recreate only analytics API/worker, restoring the caller's original value later."""
    path = directory / "batch.compose.yaml"
    path.write_text(
        "services:\n"
        + "".join(
            f'  {name}:\n    environment:\n      SINK_BATCH_MAX_ROWS: "{rows}"\n'
            for name in ("analytics", "analytics-worker")
        ),
        encoding="utf-8",
    )
    files = prototype.FILES + (("compose.retrieval.yaml",) if retrieval.enabled() else ())
    arguments = [
        "docker",
        "compose",
        "--project-name",
        postgres.PROJECT,
        *[arg for name in files for arg in ("--file", str(ROOT / "infra" / name))],
        "--file",
        str(path),
        "up",
        "-d",
        "--no-deps",
        "analytics",
        "analytics-worker",
    ]
    result = subprocess.run(
        arguments,
        cwd=ROOT,
        env={**os.environ, **prototype.environment()},
        capture_output=True,
        timeout=150,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode:
        raise RuntimeError("Analytics batch deployment failed (private output withheld)")
    runtime, deadline = Runtime(), time.monotonic() + 60
    while time.monotonic() < deadline:
        target = runtime.container("analytics-worker")
        actual = dict(item.split("=", 1) for item in target["Config"]["Env"])
        if (
            runtime.health("analytics")
            and target["State"].get("Health", {}).get("Status") == "healthy"
            and actual.get("SINK_BATCH_MAX_ROWS") == str(rows)
        ):
            return
        time.sleep(0.5)
    raise RuntimeError("Analytics readiness did not recover")


class BrokerTrail:
    def __init__(self, namespace):
        self.client = Consumer(
            {
                "bootstrap.servers": streaming.BOOTSTRAP,
                "group.id": "desktop-observer-" + uuid4().hex,
                "enable.auto.commit": False,
                "enable.auto.offset.store": False,
                "enable.partition.eof": True,
            }
        )
        targets = []
        for domain in streaming.DOMAINS[:-1]:
            topic = f"{namespace}.{domain}.v1"
            metadata = self.client.list_topics(topic, timeout=5).topics[topic]
            if metadata.error:
                raise RuntimeError("Kafka topic metadata unavailable")
            for partition in sorted(metadata.partitions):
                tp = TopicPartition(topic, partition)
                _, high = self.client.get_watermark_offsets(tp, timeout=5)
                targets.append(TopicPartition(topic, partition, high))
        self.client.assign(targets)  # No join/rebalance or mutation of application groups.
        self.events = {}

    def poll(self, run_ids):
        from shared.event_transport.consumer import raw_fingerprint

        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            message = self.client.poll(0.02)
            if message is None or message.error():
                continue
            event = json.loads(message.value())
            if event.get("run_id") not in run_ids:
                continue
            row = {
                "event": event,
                "topic": message.topic(),
                "partition": message.partition(),
                "offset": message.offset(),
                "broker_observed_at": datetime.now(UTC).isoformat(),
                "raw_sha256": raw_fingerprint(
                    message.key(), message.value(), tuple(message.headers() or [])
                ),
            }
            key = (row["topic"], row["partition"], row["offset"])
            self.events[key] = row

    def close(self):
        self.client.close()


def receipt_tail(runtime, context):
    cursor = None
    for _ in range(100):
        page = runtime.call(
            "analytics",
            "GET",
            "/internal/v1/analytics/receipts",
            context,
            params={
                "namespace": runtime.namespace,
                "limit": 1000,
                **({"after_cursor": cursor} if cursor else {}),
            },
        )
        if not page["receipts"]:
            return cursor
        cursor = page["next_cursor"]
    raise RuntimeError("Receipt preflight exceeds its 100,000 observation bound")


def trial(runtime, directory, searches, timeout):
    context = {
        "run_id": str(uuid4()),
        "user_id": "e2e-observer-" + uuid4().hex[:12],
        "correlation_id": str(uuid4()),
        "session_id": str(uuid4()),
    }
    cursor = receipt_tail(runtime, context)
    broker = BrokerTrail(runtime.namespace)
    controller = Controller(runtime, directory / "purchase")
    infrastructure = Infrastructure(runtime.namespace)
    observations, requests, receipts = [], [], {}
    observations.append(infrastructure.snapshot())
    started = time.perf_counter()
    try:
        selection = controller.prepare(Selection(scenario="purchase", mode="automated"))["run"]
        purchase_context = selection["context"]
        run_ids = {context["run_id"], purchase_context["run_id"]}
        for number in range(searches):
            before = time.perf_counter()
            body = {
                "request_id": str(uuid4()),
                "session_id": context["session_id"],
                "mode": "filter_only",
                "top_k": 5,
                "intent": {
                    "query_text": "",
                    "category": "clothing",
                    "currency": "INR",
                    "max_price_minor": 100000,
                },
            }
            result = runtime.call("catalog", "POST", "/v1/search", context, body=body)
            if any(
                h["category"] != "clothing"
                or h["price_minor"] > 100000
                or h["stock_available"] <= 0
                for h in result["hits"]
            ):
                raise RuntimeError("Independent search hard-filter check failed")
            requests.append(
                {
                    "ordinal": number,
                    "response": result,
                    "client_seconds": time.perf_counter() - before,
                    "started_elapsed": before - started,
                }
            )
        checkout_start = time.perf_counter()
        controller.trigger(selection["id"], True)
        deadline, visible_elapsed = time.monotonic() + timeout, {}
        proof = None
        while time.monotonic() < deadline:
            broker.poll(run_ids)
            page = runtime.call(
                "analytics",
                "GET",
                "/internal/v1/analytics/receipts",
                context,
                params={
                    "namespace": runtime.namespace,
                    "limit": 1000,
                    **({"after_cursor": cursor} if cursor else {}),
                },
            )
            for row in page["receipts"]:
                source = row["source"]
                receipts[(source.get("topic"), source.get("partition"), source.get("offset"))] = row
            cursor = page["next_cursor"] or cursor
            controller.observe()
            run = controller.run
            if run.get("order", {}).get("status") in {"CONFIRMED", "CANCELLED", "MANUAL_REVIEW"}:
                if run["fault_active"]:
                    controller.recover(selection["id"])
            state = controller.verify(selection["id"])["run"]
            if state["status"] not in {"Pending", "Passed"}:
                raise RuntimeError("Independent purchase reconciliation failed")
            events = list(broker.events.values())
            by_search = {r["response"]["search_id"]: [] for r in requests}
            for row in events:
                search_id = row["event"]["payload"].get("search_id")
                if search_id in by_search:
                    prior = next(
                        (
                            e
                            for e in by_search[search_id]
                            if e["event_id"] == row["event"]["event_id"]
                        ),
                        None,
                    )
                    if prior is not None and prior != row["event"]:
                        raise RuntimeError("Conflicting duplicate Kafka event")
                    if prior is None:
                        by_search[search_id].append(row["event"])
            search_ok = all(
                sorted(e["event_type"] for e in found) == ["PRODUCT_RETRIEVED", "SEARCH_REQUESTED"]
                for found in by_search.values()
            )
            terminal_seen = any(
                e["event"]["event_type"] == "ORDER_CONFIRMED"
                and e["event"]["payload"]["order_id"] == run.get("order_id")
                for e in events
            )
            event_ids = sorted({r["event"]["event_id"] for r in events})
            if event_ids:
                proof = runtime.call(
                    "analytics",
                    "POST",
                    "/internal/v1/analytics/visibility",
                    context,
                    body={"namespace": runtime.namespace, "event_ids": event_ids},
                )
                for identity in proof["visible_event_ids"] if proof["queryable"] else []:
                    visible_elapsed.setdefault(identity, time.perf_counter() - started)
            observations.append(infrastructure.snapshot())
            if (
                search_ok
                and terminal_seen
                and state["status"] == "Passed"
                and proof
                and proof["queryable"]
                and not proof["missing_event_ids"]
                and all((r["topic"], r["partition"], r["offset"]) in receipts for r in events)
            ):
                break
        else:
            raise RuntimeError("End-to-end cohort unresolved at deadline")
        # Every actual Kafka delivery must reach durable Silver and queryable Gold.
        for row in broker.events.values():
            receipt = receipts[(row["topic"], row["partition"], row["offset"])]
            if (
                receipt["event_id"] != row["event"]["event_id"]
                or receipt["raw_sha256"] != row["raw_sha256"]
                or receipt["disposition"] not in {"new_valid", "duplicate_delivery"}
                or not receipt["gold_visible_at"]
            ):
                raise RuntimeError("Kafka-to-Gold receipt identity/disposition mismatch")
            if receipt["timing_validity"] != "observed":
                raise RuntimeError("Source-to-Gold timing unavailable or a recovery upper bound")
            produced = datetime.fromisoformat(row["event"]["produced_at"].replace("Z", "+00:00"))
            visible = datetime.fromisoformat(receipt["gold_visible_at"].replace("Z", "+00:00"))
            elapsed = (visible - produced).total_seconds()
            if elapsed < 0:
                raise RuntimeError("Cross-service timer is negative")
            row["producer_to_gold_seconds"] = elapsed
            row["source_receipt"] = receipt
        for request in requests:
            found = by_search[request["response"]["search_id"]]
            completed = next(e for e in found if e["event_type"] == "PRODUCT_RETRIEVED")
            if completed["payload"]["skus"] != [h["sku"] for h in request["response"]["hits"]]:
                raise RuntimeError("Published search results differ from HTTP response")
            request["http_to_gold_upper_bound_seconds"] = (
                max(visible_elapsed[e["event_id"]] for e in found) - request["started_elapsed"]
            )
        return {
            "status": "RECONCILED",
            "searches": requests,
            "checkout_to_gold_upper_bound_seconds": time.perf_counter() - checkout_start,
            "elapsed_seconds": time.perf_counter() - started,
            "proof": proof,
            "checks": state["checks"],
            "order_id": state["order_id"],
            "resource_complete": len(observations) >= 2
            and all(o["complete"] for o in observations[1:]),
        }
    finally:
        write(directory / "kafka.json", list(broker.events.values()))
        write(directory / "receipts.json", list(receipts.values()))
        write(directory / "requests.json", requests)
        write(directory / "resources.json", observations)
        broker.close()
        controller.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulate-purchases", action="store_true", required=True)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--searches", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--out", type=Path, default=ROOT / "artifacts/end-to-end" / uuid4().hex)
    args = parser.parse_args()
    desktop_only()
    if (
        not 1 <= args.repetitions <= 3
        or not 1 <= args.searches <= 20
        or not 10 <= args.timeout_seconds <= 600
    ):
        parser.error("Repetitions 1..3 and searches 1..20 required")
    args.out = args.out.resolve()
    if not args.out.is_relative_to(ROOT / "artifacts"):
        parser.error("Evidence must stay in this Desktop checkout's artifacts")
    args.out.mkdir(parents=True, exist_ok=False)
    runtime = Runtime()
    lease = runtime.acquire_lease()
    # Controller uses the same lease during each single-purchase trial.
    lease.close()
    worker = runtime.container("analytics-worker")
    env = dict(item.split("=", 1) for item in worker["Config"]["Env"])
    original = int(env["SINK_BATCH_MAX_ROWS"])
    results = []
    manifest = {
        "status": "RUNNING",
        "scope": "real HTTP/Kafka/active-Gold finite local comparisons",
        "formal_p9_qualified": False,
        "repetitions": args.repetitions,
        "searches_per_trial": args.searches,
        "results": results,
        "limitations": [
            "Sequential finite workload, not a sustained-rate capacity claim",
            "HTTP-to-Gold timings include observer polling as upper bounds",
            "Original namespace retained; stock/ledger audited per purchase",
            "Human owner review receipts remain required for formal P9",
        ],
    }
    try:
        for rep, order in paired(args.repetitions, [1, 100]):
            for rows in order:
                directory = args.out / f"rep-{rep}-batch-{rows}"
                directory.mkdir()
                print(f"Real end-to-end repetition {rep}, sink batch {rows}", flush=True)
                set_batch(rows, directory)
                before = live_snapshot(directory / "controls-before.json")
                result = trial(runtime, directory, args.searches, args.timeout_seconds)
                after = live_snapshot(directory / "controls-after.json")
                result["max_clock_offset_bound_ms"] = max(
                    p["best"]["offset_bound_ms"]
                    for controls in (before, after)
                    for p in controls["clock"]["probes"].values()
                )
                results.append({"repetition": rep, "batch_rows": rows, **result})
                write(directory / "result.json", result)
        manifest["status"] = (
            ("MEASURED_LOCAL" if args.repetitions == 3 else "INTEGRATION_ONLY")
            if all(r["resource_complete"] for r in results)
            else "INCOMPLETE_RESOURCES"
        )
        manifest["comparison"] = compare(
            [r["checkout_to_gold_upper_bound_seconds"] for r in results if r["batch_rows"] == 1],
            [r["checkout_to_gold_upper_bound_seconds"] for r in results if r["batch_rows"] == 100],
        )
        report = [
            "# Real HTTP / Kafka / active Gold observations",
            "",
            "Finite sequential local trials. All timings are observed upper bounds. "
            "This is not a formal P9 sustained-rate or capacity result.",
            "",
            "| Repetition | Sink batch rows | Checkout to active Gold seconds | Reconciled |",
            "|---|---:|---:|---|",
        ]
        for result in results:
            report.append(
                f"| {result['repetition']} | {result['batch_rows']} | "
                f"{result['checkout_to_gold_upper_bound_seconds']:.6f} | {result['status']} |"
            )
        report += [
            "",
            "Collector status: " + manifest["status"],
            "",
            "Every event is matched by ID, raw hash and Kafka coordinate to a durable receipt "
            "and exact membership in queryable active Gold. Payment/stock checks use owner APIs.",
        ]
        (args.out / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    except BaseException as exc:
        manifest.update(status="FAILED", error_type=type(exc).__name__)
        raise
    finally:
        try:
            set_batch(original, args.out)
            manifest["original_batch_restored"] = True
        finally:
            manifest["files"] = {
                p.relative_to(args.out).as_posix(): digest(p)
                for p in args.out.rglob("*")
                if p.is_file() and p.name != "manifest.json"
            }
            write(args.out / "manifest.json", manifest)
            print(f"End-to-end evidence: {args.out} ({manifest['status']})", flush=True)
    return 0 if manifest["status"] in {"MEASURED_LOCAL", "INTEGRATION_ONLY"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
