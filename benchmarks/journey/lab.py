"""Single-use isolated fixture jobs, sharing the existing fault controller's lease."""

import copy
import json
import os
import subprocess
import threading
from pathlib import Path
from uuid import UUID, uuid4

from benchmarks.failure_demo.runtime import Unavailable
from infra import postgres

from .model import now
from .recordings import write_json

SCENARIOS = {
    "race": {
        "title": "Two shoppers, one unit",
        "purchase_count": 2,
        "explanation": "Two independent confirmed checkouts compete for one isolated unit.",
        "preconditions": (
            "Catalogue, Inventory, Payments, Orders, relays and Kafka ready; "
            "scoped success plan enabled."
        ),
        "recovery": "Finish observation and publish the isolated analytical output.",
        "verification": (
            "One confirmed sale, one stock rejection, zero overselling, "
            "one matching debit and reconciled Gold."
        ),
    },
    "duplicate": {
        "title": "Identical duplicate delivery",
        "purchase_count": 0,
        "explanation": "Deliver the exact immutable event twice at different Kafka offsets.",
        "preconditions": "Kafka, schema cache and analytical database available.",
        "recovery": "Drain and publish the isolated fixture.",
        "verification": (
            "Three deliveries, two unique Silver IDs and two logical Gold contributions."
        ),
    },
    "conflict": {
        "title": "Same ID, conflicting payload",
        "purchase_count": 0,
        "explanation": "A second delivery changes the content while retaining the first event ID.",
        "preconditions": "Kafka, schema cache and analytical database available.",
        "recovery": "Publish valid records; retain the conflicting record in quarantine.",
        "verification": (
            "EVENT_ID_CONFLICT recorded with its raw hash and locator; "
            "original contribution unchanged."
        ),
    },
    "out_of_order": {
        "title": "Out-of-order stock updates",
        "purchase_count": 0,
        "explanation": (
            "Deliver stock version 2 before version 1 to an isolated catalogue projection."
        ),
        "preconditions": (
            "Catalogue importer, stock consumer, Kafka and analytical database available."
        ),
        "recovery": "Drain the projection and publish analytics.",
        "verification": (
            "Arrival order recorded; version 2 applied; version 1 stale; newer stock preserved."
        ),
    },
    "late_event": {
        "title": "Late analytical event",
        "purchase_count": 0,
        "explanation": (
            "Publish an old event-time window, advance the watermark, "
            "then deliver another fact for the old window."
        ),
        "preconditions": "Kafka and retained Bronze/Silver/Gold store available.",
        "recovery": "Publish the late correction as a new active Gold generation.",
        "verification": (
            "Original event time retained; LATE_RECONCILIATION recorded; "
            "Gold count and revision advance."
        ),
    },
    "malformed": {
        "title": "Malformed event among valid events",
        "purchase_count": 0,
        "explanation": (
            "Place malformed JSON between two valid canonical envelopes on the same partition."
        ),
        "preconditions": "Kafka, schema cache and analytical database available.",
        "recovery": "Drain and publish valid facts; leave the malformed bytes quarantined.",
        "verification": (
            "INVALID_JSON quarantined with provenance; both valid records reach active Gold."
        ),
    },
    "replay": {
        "title": "Isolated analytical replay",
        "purchase_count": 0,
        "explanation": (
            "Rebuild a pinned original publication into a fresh replay namespace, "
            "then repeat the same replay."
        ),
        "preconditions": "Kafka, Bronze archive and an active fixture publication available.",
        "recovery": "Run the explicit isolated replay and compare results.",
        "verification": (
            "Original/replayed IDs and business values agree; repeated replay "
            "has one logical effect; no operational commands."
        ),
    },
}


class Lab:
    def __init__(self, runtime, root):
        self.runtime, self.root = runtime, Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.current = None
        self.process = None
        self.lease = None
        self.detached = False
        # Interrupted jobs are never restarted or republished automatically.
        paths = sorted(self.root.glob("*/run.json"), key=lambda p: p.stat().st_mtime)
        if paths:
            self.current = json.loads(paths[-1].read_text("utf-8"))
            if self.current.get("status") in {"Running", "Awaiting recovery"}:
                self.current.update(
                    status="Interrupted",
                    message="Observe or recover the retained fixture; no restart was submitted.",
                )
                self.detached = True
                write_json(paths[-1], self.current)
                try:
                    self.lease = self.runtime.acquire_lease()
                except Unavailable:
                    pass

    def state(self):
        with self.lock:
            if self.current:
                path = self.root / self.current["id"] / "run.json"
                if path.is_file():
                    self.current = json.loads(path.read_text("utf-8"))
                if self.detached:
                    if self.current["status"] in {"Running", "Awaiting recovery", "Interrupted"}:
                        self.current.update(
                            status="Interrupted",
                            message=(
                                "Controller interrupted. Recover the retained fixture "
                                "before starting another."
                            ),
                        )
                    else:
                        self.detached = False
                        if self.lease:
                            self.lease.close()
                            self.lease = None
                if self.process is not None and self.process.poll() is not None:
                    if self.current["status"] in {"Running", "Awaiting recovery"}:
                        self.current.update(
                            status="Unavailable",
                            message=(
                                "Fixture process exited before verification; "
                                "inspect its saved evidence."
                            ),
                        )
                        write_json(path, self.current)
                    self.process = None
                    if self.lease:
                        self.lease.close()
                        self.lease = None
            return {
                "scenarios": SCENARIOS,
                "run": copy.deepcopy(self.current),
                "observed_at": now(),
                "history": self.history(),
            }

    def history(self):
        output = []
        for path in sorted(
            self.root.glob("*/run.json"), key=lambda p: p.stat().st_mtime, reverse=True
        )[:20]:
            value = json.loads(path.read_text("utf-8"))
            output.append(
                {k: value.get(k) for k in ("id", "scenario", "namespace", "started_at", "status")}
            )
        return output

    def start(self, scenario, confirmed):
        if scenario not in SCENARIOS or confirmed is not True:
            raise ValueError(
                "Choose a known scenario and explicitly confirm its controlled fixture"
            )
        with self.lock:
            self.state()
            if self.process is not None or self.detached:
                raise ValueError("Recover and finish the active fixture before starting another")
            lease = self.runtime.acquire_lease()
            try:
                for service in ("catalog", "orders", "inventory", "payments", "analytics"):
                    if self.runtime.health(service) is not True:
                        raise Unavailable(f"{service} readiness prerequisite is not met")
                identity = str(uuid4())
                namespace = "bench-journey-" + UUID(identity).hex[:16]
                folder = self.root / identity
                folder.mkdir()
                self.current = {
                    "id": identity,
                    "scenario": scenario,
                    "namespace": namespace,
                    "status": "Running",
                    "started_at": now(),
                    "observations": [],
                    "checks": [],
                    "events": [],
                    "message": "Starting isolated owner-backed fixture.",
                    "purchase_count": SCENARIOS[scenario]["purchase_count"],
                    "mode": "real_isolated_fixture",
                    "recovery_requested": False,
                }
                write_json(folder / "run.json", self.current)
                name = "group3-journey-" + UUID(identity).hex[:12]
                self.current["container_name"] = name
                write_json(folder / "run.json", self.current)
                from infra import prototype

                configured = prototype.environment(host=False)
                values = {
                    k: v
                    for k, v in configured.items()
                    if k.endswith("_DATABASE_URL")
                    or k in {"CODE_COMMIT", "INTERNAL_API_TOKEN", "CATALOG_DATASET_REVISION"}
                }
                values.update(
                    {
                        "RUN_NAMESPACE": namespace,
                        "RUN_ID": identity,
                        "LAKEHOUSE_ROOT": "/lakehouse",
                        "EVENT_SCHEMA_CACHE_PATH": "/app/schema-cache.json",
                        "KAFKA_BOOTSTRAP_SERVERS": "kafka:9092",
                        "SINK_BATCH_MAX_ROWS": "100",
                        "CATALOG_BASE_URL": "http://catalog:8002",
                        "PYTHONPYCACHEPREFIX": "/tmp/journey-pycache",
                    }
                )
                args = [
                    "docker",
                    "run",
                    "--rm",
                    "--name",
                    name,
                    "--label",
                    "com.docker.compose.project=" + postgres.PROJECT,
                    "--label",
                    "group3.owner=jaineel",
                    "--label",
                    "group3.journey.fixture=" + identity,
                    "--network",
                    postgres.PROJECT + "_default",
                    "--memory",
                    "768m",
                    "--cpus",
                    "1",
                    "--pids-limit",
                    "128",
                    "--volumes-from",
                    self.runtime.container("analytics-worker")["Id"],
                ]
                for directory in (
                    "benchmarks",
                    "configs",
                    "projectctl",
                    "infra",
                    "services",
                    "migrations",
                ):
                    args.extend(
                        [
                            "--mount",
                            f"type=bind,source={postgres.ROOT / directory},"
                            f"target=/app/{directory},readonly",
                        ]
                    )
                args.extend(["--mount", f"type=bind,source={folder},target=/journey-output"])
                for key in sorted(values):
                    args.extend(["-e", key])
                args.extend(
                    [
                        "group3-m04-storage:local",
                        "python",
                        "-m",
                        "benchmarks.journey.lab_worker",
                        "--scenario",
                        scenario,
                        "--id",
                        identity,
                        "--namespace",
                        namespace,
                    ]
                )
                with (folder / "worker.log").open("w", encoding="utf-8") as log:
                    self.process = subprocess.Popen(
                        args,
                        cwd=postgres.ROOT,
                        env={**os.environ, **values},
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                self.lease = lease
                self.current["container_name"] = name
                return self.state()
            except Exception:
                lease.close()
                raise

    def recover(self, identity):
        with self.lock:
            if not self.current or self.current["id"] != str(identity):
                raise ValueError("Selected fixture is no longer current")
            if self.detached:
                # A retained fixture may outlive its controller, but never restart it.
                name = "group3-journey-" + UUID(str(identity)).hex[:12]
                ids = self.runtime.docker(
                    "ps",
                    "-q",
                    "--filter",
                    "name=^/" + name + "$",
                    "--filter",
                    "label=group3.journey.fixture=" + str(identity),
                    "--filter",
                    "label=com.docker.compose.project=" + postgres.PROJECT,
                )
                if not ids:
                    self.current.update(
                        status="Unavailable",
                        message=(
                            "Interrupted fixture has no running worker; "
                            "retained evidence is incomplete."
                        ),
                    )
                    write_json(self.root / str(identity) / "run.json", self.current)
                    self.detached = False
                    if self.lease:
                        self.lease.close()
                        self.lease = None
                    return self.state()
            path = self.root / str(UUID(str(identity))) / "recover.request"
            path.write_text(now(), encoding="utf-8")
            return self.state()

    def evidence(self, identity):
        path = self.root / str(UUID(str(identity))) / "run.json"
        return json.loads(path.read_text("utf-8"))

    def shutdown(self):
        with self.lock:
            if self.current and self.process is not None:
                self.recover(self.current["id"])
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    # Stop only the worker bound to this exact retained fixture.
                    name = "group3-journey-" + UUID(self.current["id"]).hex[:12]
                    self.runtime.docker("stop", "--time", "5", name)
                    self.process.wait(timeout=10)
                finally:
                    self.state()
