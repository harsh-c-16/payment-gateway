"""Real isolated fixture composition using owner-provided import/seed/pipeline APIs.

Run only in the controller's disposable Linux container. Never runs on page load.
No business rules are implemented here; expected values form an independent oracle.
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient, NewTopic

from pipelines.ingestion.runtime import pipeline_from_env
from pipelines.storage.readers import receipts
from shared.event_transport import ConsumerGroup, EventCodec, KafkaPublisher
from shared.event_transport.schemas import SchemaCache

from .model import now, safe_event
from .recordings import write_json

OUTPUT = Path("/journey-output")
DOMAINS = (
    "conversation-events",
    "retrieval-events",
    "order-events",
    "inventory-events",
    "payment-events",
    "dead-letter",
)
PORTS = {
    "store": "conversation:8001",
    "catalog": "catalog:8002",
    "orders": "orders:8003",
    "inventory": "inventory:8004",
    "payments": "payments:8005",
    "analytics": "analytics:8006",
}


class Fixture:
    def __init__(self, arguments):
        self.args = arguments
        if not arguments.namespace.startswith("bench-journey-") or sys.platform != "linux":
            raise ValueError("Isolated Linux journey fixture required")
        self.ns, self.identity = arguments.namespace, arguments.id
        self.run = json.loads((OUTPUT / "run.json").read_text("utf-8"))
        self.run["fixture_version"] = "journey-edge-v1"
        self.context = {
            "namespace": self.ns,
            "run_id": self.identity,
            "user_id": "edge-lab-" + self.identity[:8],
            "session_id": str(uuid4()),
            "correlation_id": str(uuid4()),
            "request_id": str(uuid4()),
        }
        self.codec = EventCodec(
            SchemaCache.load(os.environ["EVENT_SCHEMA_CACHE_PATH"]),
            source_service="benchmark",
            dataset_revision=os.environ["CATALOG_DATASET_REVISION"],
        )
        self.pipeline = pipeline_from_env()
        self.publisher = KafkaPublisher(self.codec, os.environ["KAFKA_BOOTSTRAP_SERVERS"])
        self.group, self.projection = None, None
        self.started = time.monotonic()
        self.run.update(emissions=[], checks=[], journal=[], receipts=[], requests=[], events=[])

    def save(self, message=None):
        if message:
            self.run["message"] = message
            self.run["journal"].append({"at": now(), "message": message})
        self.run["observed_at"] = now()
        write_json(OUTPUT / "run.json", self.run)

    def check(self, name, expected, observed):
        self.run["checks"].append(
            {
                "name": name,
                "expected": expected,
                "observed": observed,
                "passed": observed == expected if observed is not None else None,
            }
        )
        self.save()

    def api(self, role, method, path, body=None, context=None, key=None, request_id=None):
        context = context or self.context
        headers = {
            "X-Namespace": self.ns,
            "X-Run-ID": self.identity,
            "X-User-ID": context["user_id"],
            "X-Session-ID": context["session_id"],
            "X-Correlation-ID": context["correlation_id"],
            "X-Request-ID": request_id or str(uuid4()),
            "Authorization": "Bearer " + os.environ["INTERNAL_API_TOKEN"],
        }
        if method != "GET":
            headers["Idempotency-Key"] = key or str(uuid4())
        response = httpx.request(
            method,
            "http://" + PORTS[role] + path,
            headers=headers,
            json=body,
            timeout=10,
            trust_env=False,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"{role} API returned HTTP {response.status_code}")
        return response.json()

    def topics(self):
        admin = AdminClient({"bootstrap.servers": os.environ["KAFKA_BOOTSTRAP_SERVERS"]})
        requested = [
            NewTopic(f"{self.ns}.{domain}.v1", num_partitions=1, replication_factor=1)
            for domain in DOMAINS
        ]
        for result in admin.create_topics(requested, request_timeout=10).values():
            result.result(12)
        self.group = ConsumerGroup(
            self.ns + ".analytics.v1",
            [f"{self.ns}.{domain}.v1" for domain in DOMAINS[:-1]],
            os.environ["KAFKA_BOOTSTRAP_SERVERS"],
        )
        self.save("Fresh isolated topics created; no production consumer offsets changed.")

    def turn(self, version, event_time=None):
        return self.codec.build_event(
            "CONVERSATION_TURN",
            {
                "turn_id": str(uuid4()),
                "mode": "fixed",
                "outcome": "success",
                "duration_ms": 1.0,
                "llm_call_count": 0,
                "extractor_source": "rules",
            },
            self.context,
            "session",
            self.context["session_id"],
            version,
            event_time or datetime.now(UTC),
            metadata={"synthetic": True, "scenario_source": "benchmark"},
        )

    def emit(self, event, scheduled_at=None, malformed=False):
        index = len(self.run["emissions"])
        plan = self.run.get("planned_emissions", [])
        planned = scheduled_at or (plan[index]["scheduled_at"] if index < len(plan) else None)
        if planned:
            due = datetime.fromisoformat(planned).timestamp() - time.time()
            if due > 0:
                time.sleep(min(due, 1))
        entry = {
            "event_id": None if malformed else event.event_id,
            "scheduled_at": planned,
            "sent_at": now(),
            "broker_acked_at": None,
            "source": None,
            "kind": "malformed_fixture" if malformed else "canonical_fixture",
        }
        self.run["emissions"].append(entry)
        self.save("Offered fixture delivery; acknowledgement remains pending.")
        if malformed:
            raw, headers, topic, key = self.codec.encode(event)
            producer = Producer(
                {
                    "bootstrap.servers": os.environ["KAFKA_BOOTSTRAP_SERVERS"],
                    "enable.idempotence": True,
                    "acks": "all",
                }
            )
            ack, errors = [], []

            def delivered(error, message):
                if error:
                    errors.append(str(error))
                else:
                    ack.append(
                        {
                            "topic": message.topic(),
                            "partition": message.partition(),
                            "offset": message.offset(),
                        }
                    )

            producer.produce(
                topic, key=key, value=b'{"malformed":', headers=list(headers), on_delivery=delivered
            )
            if producer.flush(12) or errors or not ack:
                raise RuntimeError("Malformed fixture Kafka acknowledgement unavailable")
            entry["source"] = ack[0]
        else:
            ack = self.publisher.publish_event(event, event.topic(), event.kafka_key(), timeout=12)
            entry["source"] = {"topic": ack.topic, "partition": ack.partition, "offset": ack.offset}
            self.run["events"].append(safe_event(event.model_dump(mode="json")))
        entry["broker_acked_at"] = now()
        self.save("Kafka delivery acknowledged at its exact topic / partition / offset.")

    def drain(self, expected, publish=True, timeout=45):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.pipeline.ingest_once(self.group, run_id=self.identity, max_records=100)
            page = receipts(self.pipeline.connect, self.ns, limit=1000)
            unique = {
                (r.source.topic, r.source.partition, r.source.offset): r for r in page.receipts
            }
            self.run["receipts"] = [r.model_dump(mode="json") for r in unique.values()]
            if publish and unique:
                try:
                    manifest = self.pipeline.publish_snapshot(self.ns)
                    self.run["gold_generation"] = manifest.generation
                except LookupError:
                    pass
            self.save("Observed durable source dispositions and publication state.")
            if len(unique) >= expected and all(r.disposition is not None for r in unique.values()):
                if not publish or all(
                    r.gold_visible_at or r.disposition == "invalid" for r in unique.values()
                ):
                    return
            time.sleep(0.1)
        raise TimeoutError("Fixture did not drain within its observation deadline")

    def await_recovery(self):
        self.run["status"] = "Awaiting recovery"
        self.save(
            "Fixture observed. Press Recover / publish to finish; "
            "automatic recovery after 90 seconds is recorded."
        )
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline and not (OUTPUT / "recover.request").is_file():
            time.sleep(0.25)
        self.run["recovery_requested"] = (OUTPUT / "recover.request").is_file()
        self.run["automatic_recovery"] = not self.run["recovery_requested"]
        self.run["status"] = "Running"
        self.save(
            "Recovery / publication explicitly requested."
            if self.run["recovery_requested"]
            else "90-second recovery deadline reached; finishing isolated publication."
        )

    def catalogue(self, seed=False):
        # Owner setup adapters create an explicitly synthetic one-row catalogue.
        from pipelines.catalog.adapter import run_import
        from projectctl.providers import Invocation
        from services.inventory.adapter import inventory_seed

        source = Path("/app/contracts/fixtures/journey/catalog.csv")
        report, _ = run_import(
            source, load_mode="copy", namespace=self.ns, out=OUTPUT / "catalogue"
        )
        self.run["catalogue_import"] = report.model_dump(mode="json")
        manifest = json.loads((OUTPUT / "catalogue/sku_manifest.json").read_text("utf-8"))
        self.codec.dataset_revision = manifest["dataset_revision"]
        os.environ["CATALOG_DATASET_REVISION"] = manifest["dataset_revision"]
        if seed:
            invocation = Invocation(
                "inventory seed",
                {
                    "profile": "test",
                    "sku_manifest": str(OUTPUT / "catalogue/sku_manifest.json"),
                    "seed": 42,
                },
                None,
                self.identity,
                self.ns,
            )
            result = inventory_seed(invocation)
            if result.code != 0:
                raise RuntimeError("Owner test-profile one-unit inventory seed failed")
        log = (OUTPUT / "projection.log").open("w", encoding="utf-8")
        self.projection = subprocess.Popen(
            [sys.executable, "-m", "services.catalog.worker", "--namespace", self.ns],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        log.close()
        self.save(
            "Synthetic one-row catalogue prepared through the owner's importer; "
            "stock consumer started in isolation."
        )

    def race(self):
        self.catalogue(seed=True)
        sku = "FK-JOURNEYLAB000001"
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            product = self.api("catalog", "GET", "/v1/products/" + sku)
            if (product.get("stock") or {}).get("available") == 1:
                break
            time.sleep(0.25)
        else:
            raise TimeoutError("One-unit projection did not become available")
        self.api(
            "payments",
            "POST",
            "/internal/v1/demo-control",
            {
                "run_id": self.identity,
                "namespace": self.ns,
                "scenario": "success",
                "expires_at": (datetime.now(UTC) + timedelta(seconds=220)).isoformat(),
            },
        )
        prepared = []
        for index in range(2):
            context = {
                **self.context,
                "user_id": f"lab-shopper-{index}",
                "session_id": str(uuid4()),
            }
            session = self.api("store", "POST", "/v1/sessions", {}, context)
            context["session_id"] = session["session_id"]
            cart = self.api(
                "store",
                "PUT",
                f"/v1/carts/{session['cart_id']}/items/{sku}",
                {"quantity": 1, "expected_cart_version": 0},
                context,
            )
            quote = self.api(
                "store",
                "POST",
                f"/v1/carts/{session['cart_id']}/quote",
                {"expected_cart_version": cart["version"]},
                context,
            )
            prepared.append(
                (
                    context,
                    session["cart_id"],
                    {
                        "quote_id": quote["quote_id"],
                        "expected_cart_version": cart["version"],
                        "confirmed": True,
                        "confirmation_id": str(uuid4()),
                    },
                )
            )
        barrier = threading.Barrier(2)

        def checkout(value):
            context, cart, body = value
            barrier.wait(timeout=10)
            request = {
                "submitted_at": now(),
                "user_id": context["user_id"],
                "request_id": str(uuid4()),
                "key": str(uuid4()),
            }
            result = self.api(
                "store",
                "POST",
                f"/v1/carts/{cart}/checkout",
                body,
                context,
                request["key"],
                request["request_id"],
            )
            request.update(order_id=result["order_id"], acknowledged_at=now())
            return request

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.run["requests"] = list(pool.map(checkout, prepared))
        deadline = time.monotonic() + 75
        orders = []
        while time.monotonic() < deadline:
            orders = [
                self.api("orders", "GET", "/v1/orders/" + r["order_id"], context=c)
                for r, (c, _, _) in zip(self.run["requests"], prepared, strict=True)
            ]
            stock = self.api("inventory", "GET", "/internal/v1/inventory/" + sku)
            self.run["observations"].append({"at": now(), "orders": orders, "stock": stock})
            self.save(
                "Both real Orders sagas observed; authoritative stock inspected independently."
            )
            if all(
                order["status"] in {"CONFIRMED", "CANCELLED", "MANUAL_REVIEW"} for order in orders
            ):
                break
            time.sleep(0.5)
        self.check("Exactly one confirmed sale", 1, sum(o["status"] == "CONFIRMED" for o in orders))
        self.check("Competing order cancelled", 1, sum(o["status"] == "CANCELLED" for o in orders))
        self.check(
            "No overselling; last unit consumed",
            [0, 0, 0],
            [stock["on_hand"], stock["reserved"], stock["available"]],
        )
        ledger = self.api("payments", "GET", "/internal/v1/audit/ledger")["items"]
        self.run["ledger"] = ledger
        self.check(
            "One debit for the confirmed order", 1, sum(e["kind"] == "DEBIT" for e in ledger)
        )
        confirmed = next((o for o in orders if o["status"] == "CONFIRMED"), None)
        self.check(
            "Debit identity and immutable total",
            True,
            bool(confirmed)
            and all(
                e["order_id"] == confirmed["order_id"]
                and e["amount_minor"] == confirmed["total_amount_minor"]
                for e in ledger
            ),
        )
        self.run["orders"] = orders
        self.await_recovery()
        # Relays run independently; wait until both terminal event IDs are durable.
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            self.pipeline.ingest_once(self.group, run_id=self.identity, max_records=100)
            self.pipeline.publish_snapshot(self.ns)
            day = datetime.now(UTC).date()
            result = self.pipeline.query_gold(self.ns, "order_fact", day, day + timedelta(days=1))
            facts = {r["order_id"]: r for r in result.rows}
            if all(
                o["order_id"] in facts
                and facts[o["order_id"]]["order_version"] == o["order_version"]
                for o in orders
            ):
                break
            time.sleep(0.25)
        self.run["business_result"] = result.model_dump(mode="json")
        self.check(
            "Both terminal orders exactly reconciled in active Gold",
            True,
            all(
                o["order_id"] in facts
                and all(
                    facts[o["order_id"]].get(k if k != "status" else "order_status") == o[k]
                    for k in ("order_version", "status", "total_amount_minor", "currency")
                )
                for o in orders
            ),
        )

    def quality(self):
        scenario = self.args.scenario
        count = 3 if scenario in {"duplicate", "conflict", "malformed", "late_event"} else 2
        start = datetime.now(UTC)
        self.run["measurement_window"] = {
            "started_at": start.isoformat(),
            "ended_at": (start + timedelta(seconds=5)).isoformat(),
            "scope": "Finite scheduled fixture; completions during subsequent drain are excluded",
        }
        self.run["planned_emissions"] = [
            {"slot": i, "scheduled_at": (start + timedelta(seconds=0.25 * i)).isoformat()}
            for i in range(count)
        ]
        self.save("Intended fixture schedule frozen before sends; delays remain measurable.")
        a, b = self.turn(1), self.turn(2)
        if scenario == "late_event":
            old = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(minutes=5)
            a, b = self.turn(1, old), self.turn(3, old + timedelta(seconds=1))
            self.emit(a)
            self.drain(1)
            before = self.pipeline.query_gold(
                self.ns, "pipeline_minute", old.date(), old.date() + timedelta(days=1)
            )
            self.run["before_business_result"] = before.model_dump(mode="json")
            self.emit(self.turn(2))
            self.drain(2)
            self.emit(b)
            self.drain(3, publish=False)
        elif scenario == "out_of_order":
            self.catalogue()
            sku = "FK-JOURNEYLAB000001"
            for version, available in ((2, 4), (1, 9)):
                event = self.codec.build_event(
                    "STOCK_UPDATED",
                    {
                        "sku": sku,
                        "on_hand": available,
                        "reserved": 0,
                        "available": available,
                        "stock_version": version,
                        "changed_at": now(),
                        "order_id": None,
                        "reservation_id": None,
                        "reason_code": None,
                    },
                    self.context,
                    "sku",
                    sku,
                    version,
                    now(),
                    metadata={"synthetic": True, "scenario_source": "benchmark"},
                    source_service="inventory",
                )
                self.emit(event)
            self.drain(2, publish=False)
        else:
            self.emit(a)
            if scenario == "duplicate":
                self.emit(a)
            elif scenario == "conflict":
                conflict = a.model_copy(update={"payload": {**a.payload, "duration_ms": 99.0}})
                self.emit(conflict)
            elif scenario == "malformed":
                self.emit(a, malformed=True)
            self.emit(b)
            self.drain(
                3 if scenario in {"duplicate", "conflict", "malformed"} else 2, publish=False
            )
        self.await_recovery()
        count = 3 if scenario in {"duplicate", "conflict", "malformed", "late_event"} else 2
        self.drain(count)
        page = receipts(self.pipeline.connect, self.ns, limit=1000)
        unique = {(r.source.topic, r.source.partition, r.source.offset): r for r in page.receipts}
        dispositions = Counter(r.disposition for r in unique.values())
        self.run["dispositions"] = dict(dispositions)
        self.check("Every offered delivery durably classified", count, len(unique))
        expected = (
            {"new_valid": 2, "duplicate_delivery": 1}
            if scenario == "duplicate"
            else {"new_valid": 2, "invalid": 1}
            if scenario in {"conflict", "malformed"}
            else {"new_valid": count}
        )
        self.check("Independent expected source dispositions", expected, dict(dispositions))
        if scenario in {"conflict", "malformed"}:
            self.check(
                "Recorded quarantine reason",
                "EVENT_ID_CONFLICT" if scenario == "conflict" else "INVALID_JSON",
                next((r.reason_code for r in unique.values() if r.disposition == "invalid"), None),
            )
        with self.pipeline.connect() as tx:
            logical = tx.execute(
                "SELECT count(*) FROM silver_events WHERE namespace=%s", (self.ns,)
            ).fetchone()[0]
        self.check("One Silver row per logical valid event", expected["new_valid"], logical)
        event_day = (datetime.now(UTC) - timedelta(minutes=5)).date()
        result = self.pipeline.query_gold(
            self.ns, "pipeline_minute", event_day, datetime.now(UTC).date() + timedelta(days=1)
        )
        self.run["business_result"] = result.model_dump(mode="json")
        self.check(
            "One Gold contribution per unique valid ID",
            expected["new_valid"],
            sum(r["unique_events"] for r in result.rows),
        )
        if scenario == "out_of_order":
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                projection = self.api("catalog", "GET", "/internal/v1/projection/receipts")[
                    "receipts"
                ]
                if len(projection) >= 2:
                    break
                time.sleep(0.25)
            self.run["projection_receipts"] = projection
            self.check(
                "Version 2 applied before version 1 rejected as stale",
                ["applied", "stale"],
                [r["outcome"] for r in projection],
            )
            stock = self.api("catalog", "GET", "/v1/products/FK-JOURNEYLAB000001").get("stock")
            self.run["projected_stock"] = stock
            self.check(
                "Newer projection preserved",
                [2, 4],
                [stock["stock_version"], stock["available"]] if stock else None,
            )
        if scenario == "late_event":
            with self.pipeline.connect() as tx:
                flags = tx.execute(
                    "SELECT timestamp_quality,reason FROM event_time_observations "
                    "WHERE namespace=%s AND event_id=%s",
                    (self.ns, b.event_id),
                ).fetchone()
            self.run["late_observation"] = list(flags) if flags else None
            self.check(
                "Late reconciliation reason", "LATE_RECONCILIATION", flags[1] if flags else None
            )
            before = self.run["before_business_result"]["rows"][0]
            revised = next((r for r in result.rows if r["minute"] == before["minute"]), None)
            self.check(
                "Published old window revised from one to two events",
                2,
                revised["unique_events"] if revised else None,
            )
            self.check(
                "Revision increased in a newer generation",
                True,
                revised["revision"] > before["revision"]
                and result.generation > self.run["before_business_result"]["generation"]
                if revised
                else None,
            )
        if scenario == "replay":
            self.replay(result)

    def replay(self, original):
        from pipelines.replay.jobs import create_replay, run_replay

        manifest = self.pipeline.active_manifest(self.ns, "gold")
        target = "replay-journey-" + uuid4().hex[:16]
        job = create_replay(
            self.pipeline,
            {
                "source_manifest_ids": manifest.input_manifest_ids,
                "target_namespace": target,
                "transform_version": self.pipeline.transform_version,
            },
        )
        first = run_replay(self.pipeline, job.replay_id)
        again = run_replay(self.pipeline, job.replay_id)
        replayed = self.pipeline.query_gold(
            target,
            "pipeline_minute",
            datetime.now(UTC).date() - timedelta(days=1),
            datetime.now(UTC).date() + timedelta(days=1),
        )

        def business(rows):
            return sorted(
                [{k: v for k, v in r.items() if k not in {"namespace", "revision"}} for r in rows],
                key=lambda r: json.dumps(r, sort_keys=True),
            )

        self.run["replay"] = {
            "target_namespace": target,
            "first": first.model_dump(mode="json"),
            "repeated": again.model_dump(mode="json"),
            "result": replayed.model_dump(mode="json"),
            "operational_commands": 0,
            "republished_events": 0,
        }
        self.check(
            "Replay completed and reconciled",
            True,
            first.status == "COMPLETED" and first.reconciliation.passed,
        )
        self.check(
            "Independent original / replay business equality",
            business(original.rows),
            business(replayed.rows),
        )
        self.check("Repeated replay keeps one logical effect", "COMPLETED", again.status)

    def execute(self):
        try:
            self.topics()
            if self.args.scenario == "race":
                self.race()
            else:
                self.quality()
            self.run["status"] = (
                "Passed"
                if self.run["checks"] and all(c["passed"] is True for c in self.run["checks"])
                else "Failed"
            )
            self.save(
                "Independent fixture verification finished; "
                "inspect every assertion and retained source identity."
            )
        except Exception as error:
            self.run.update(
                status="Unavailable"
                if isinstance(error, (OSError, TimeoutError, httpx.HTTPError))
                else "Failed",
                error_type=type(error).__name__,
            )
            self.save(
                "Fixture could not complete. No pass is inferred; private process log retained."
            )
            print(type(error).__name__, flush=True)
            traceback.print_exc()
        finally:
            if self.args.scenario == "race":
                try:
                    self.api("payments", "DELETE", "/internal/v1/demo-control/" + self.identity)
                except Exception:
                    self.run["recovery_warning"] = (
                        "Scoped payment plan not cleared; it expires automatically."
                    )
            if self.projection:
                self.projection.terminate()
                try:
                    self.projection.wait(8)
                except subprocess.TimeoutExpired:
                    self.projection.kill()
                    self.projection.wait(5)
            if self.group:
                self.group.close()
            self.publisher.close()
            self.run["completed_at"] = now()
            self.run["elapsed_seconds"] = time.monotonic() - self.started
            self.save()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--id", required=True)
    Fixture(parser.parse_args()).execute()


if __name__ == "__main__":
    main()
