"""Fixed project process actions and read-only owner API audit collection."""

import io
import json
import socket
import subprocess
import tarfile
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx

from infra import postgres, prototype

ROOT = postgres.ROOT
PORTS = {
    "store": 8001,
    "catalog": 8002,
    "orders": 8003,
    "inventory": 8004,
    "payments": 8005,
    "analytics": 8006,
}


def now():
    return datetime.now(UTC).isoformat()


class Unavailable(RuntimeError):
    pass


class ResponseLost(RuntimeError):
    """Injected gateway failure after a committed real backend acknowledgement."""


class Runtime:
    def __init__(self):
        self.values = prototype.environment(host=True)
        self.namespace = self.values["RUN_NAMESPACE"]

    def acquire_lease(self):
        """One active fault trial across browser and CLI controllers on this desktop."""
        lease = socket.socket()
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            lease.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            lease.bind(("127.0.0.1", 8011))
        except OSError as exc:
            lease.close()
            raise Unavailable("Another desktop failure run holds the local scenario lease") from exc
        return lease

    def docker(self, *args, binary=False):
        try:
            result = subprocess.run(
                ["docker", *args], cwd=ROOT, capture_output=True, timeout=25, check=True
            )
            return result.stdout if binary else result.stdout.decode("utf-8").strip()
        except (subprocess.SubprocessError, OSError) as exc:
            # Docker errors can include environment bindings. Keep them out of UI/evidence.
            raise Unavailable("Project Docker action failed or exceeded 25 seconds") from exc

    def container(self, service):
        if service not in {"analytics-worker", "orders", "payments", "conversation"}:
            raise Unavailable("Unsupported project target")
        ids = self.docker(
            "ps",
            "-aq",
            "--filter",
            f"label=com.docker.compose.project={postgres.PROJECT}",
            "--filter",
            f"label=com.docker.compose.service={service}",
        ).splitlines()
        if len(ids) != 1:
            raise Unavailable(f"Expected one project {service} container")
        record = json.loads(self.docker("inspect", ids[0]))[0]
        labels = record["Config"].get("Labels", {})
        mounts = record.get("Mounts", [])
        source_dir = "pipelines" if service == "analytics-worker" else "services"
        expected = str(ROOT / source_dir).replace("\\", "/").lower()

        def source_path(value):
            normalized = value.replace("\\", "/").lower()
            for prefix in ("/run/desktop/mnt/host/", "/host_mnt/"):
                if normalized.startswith(prefix):
                    suffix = normalized[len(prefix) :]
                    normalized = suffix[0] + ":" + suffix[1:]
            return normalized

        if (
            labels.get("com.docker.compose.project") != postgres.PROJECT
            or labels.get("com.docker.compose.service") != service
            or not any(
                m["Destination"] == "/app/" + source_dir
                and source_path(m["Source"]) == expected
                and m["RW"] is False
                for m in mounts
            )
        ):
            raise Unavailable("Container does not mount this checkout's owner code read-only")
        return record

    def worker_state(self):
        record = self.container("analytics-worker")
        state = record["State"]
        return {
            "paused": state["Paused"],
            "running": state["Running"],
            "container_id": record["Id"][:12],
        }

    def process(self, service, action):
        if (service, action) not in {
            ("analytics-worker", "pause"),
            ("analytics-worker", "unpause"),
            ("orders", "start"),
        }:
            raise Unavailable("Unsupported project action")
        record = self.container(service)
        if action == "unpause" and not record["State"]["Paused"]:
            return
        if action == "start" and record["State"]["Running"]:
            return
        self.docker(action, record["Id"])

    def checkpoint(self, run_id):
        record = self.container("orders")
        if record["State"]["Running"]:
            return None
        raw = self.docker(
            "cp",
            record["Id"] + ":/tmp/shoptalk-failure-demo/orders/" + run_id + ".checkpoint",
            "-",
            binary=True,
        )
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
            members = archive.getmembers()
            if len(members) != 1 or members[0].size > 4096 or not members[0].isfile():
                raise Unavailable("Invalid checkpoint acknowledgement")
            value = json.load(archive.extractfile(members[0]))
        if value.get("run_id") != run_id or value.get("checkpoint") != "saga.after_commit":
            raise Unavailable("Checkpoint identity mismatch")
        return {
            **value,
            "exit_code": record["State"]["ExitCode"],
            "container_id": record["Id"][:12],
        }

    def headers(self, context, *, request_id=None, key=None):
        headers = {
            "X-Namespace": self.namespace,
            "X-Run-ID": context["run_id"],
            "X-User-ID": context["user_id"],
            "X-Correlation-ID": context["correlation_id"],
            "X-Request-ID": request_id or str(uuid4()),
            "Authorization": "Bearer " + self.values["INTERNAL_API_TOKEN"],
        }
        if context.get("session_id"):
            headers["X-Session-ID"] = context["session_id"]
        if key:
            headers["Idempotency-Key"] = key
        return headers

    def call(
        self,
        service,
        method,
        path,
        context,
        *,
        body=None,
        params=None,
        request_id=None,
        key=None,
        optional=False,
    ):
        if (
            service not in PORTS
            or not path.startswith("/v1/")
            and not path.startswith("/internal/v1/")
        ):
            raise Unavailable("Unsupported owner API")
        try:
            response = httpx.request(
                method,
                f"http://127.0.0.1:{PORTS[service]}{path}",
                headers=self.headers(context, request_id=request_id, key=key),
                json=body,
                params=params,
                timeout=10,
                trust_env=False,
                follow_redirects=False,
            )
            if response.status_code >= 400:
                raise Unavailable(f"{service} {method} {path}: HTTP {response.status_code}")
            return response.json()
        except (httpx.HTTPError, ValueError, Unavailable) as exc:
            if optional:
                return None
            if isinstance(exc, Unavailable):
                raise
            raise Unavailable(f"{service} API could not be measured") from exc

    def health(self, service):
        try:
            response = httpx.get(
                f"http://127.0.0.1:{PORTS[service]}/health/ready", timeout=2, trust_env=False
            )
            return response.status_code == 200 and response.json().get("status") == "ready"
        except (httpx.HTTPError, ValueError):
            return None

    def arm(self, role, context, scenario):
        return self.call(
            role,
            "POST",
            "/internal/v1/demo-control",
            context,
            body={
                "run_id": context["run_id"],
                "namespace": self.namespace,
                "scenario": scenario,
                "expires_at": (datetime.now(UTC) + timedelta(seconds=240)).isoformat(),
            },
        )

    def clear(self, role, context):
        return self.call(role, "DELETE", "/internal/v1/demo-control/" + context["run_id"], context)

    def orders(self, context):
        result = self.call(
            "orders", "GET", "/internal/v1/audit/orders", context, params={"limit": 1000}
        )
        if result["count"] >= 1000 or result["count"] != len(result["items"]):
            raise Unavailable("Order audit reached its 1,000-row sample bound")
        return result["items"]

    def stock(self, context, sku):
        return self.call("inventory", "GET", "/internal/v1/inventory/" + sku, context)

    def audit(self, context, order):
        oid = order["order_id"]
        reservation = self.call(
            "inventory", "GET", "/internal/v1/reservations/by-order/" + oid, context, optional=True
        )
        payments = self.call(
            "payments", "GET", "/internal/v1/payments/by-order/" + oid, context, optional=True
        )
        ledger = self.call("payments", "GET", "/internal/v1/audit/ledger", context, optional=True)
        entries = [r for r in ledger["items"] if r["order_id"] == oid] if ledger else None
        stocks = {line["sku"]: self.stock(context, line["sku"]) for line in order["lines"]}
        return {
            "reservation": reservation,
            "payments": payments,
            "ledger": entries,
            "stocks": stocks,
            "observed_at": now(),
        }


def verify_effects(run):
    """Independent checks of immutable identity, signed ledger and stock deltas."""
    checks = []

    def check(name, expected, actual):
        checks.append(
            {
                "name": name,
                "expected": expected,
                "observed": actual,
                "passed": None if actual is None else actual == expected,
            }
        )

    order, audit = run.get("order"), run.get("audit")
    if not order or not audit:
        check("Terminal order and owner audit available", True, None)
        return checks
    expected = "CANCELLED" if run["scenario"] in {"decline", "late", "refund"} else "CONFIRMED"
    check("Terminal order state", expected, order["status"])
    scoped = [
        r
        for r in run.get("current_orders", [])
        if r["user_id"] == run["context"]["user_id"]
        and r["session_id"] == run["context"]["session_id"]
        and r["order_id"] not in run["baseline_orders"]
    ]
    check(
        "Exactly one new purchase for watched session",
        [order["order_id"]],
        [r["order_id"] for r in scoped],
    )
    check(
        "Immutable checkout identity",
        True,
        all(order.get(k) == v for k, v in run["immutable"].items())
        if run.get("immutable")
        else None,
    )
    reservation, payments, ledger = audit["reservation"], audit["payments"], audit["ledger"]
    check(
        "Reservation has one committed or released effect",
        True,
        reservation["state"]
        in ({"COMMITTED"} if expected == "CONFIRMED" else {"RELEASED", "EXPIRED"})
        if reservation
        else None,
    )
    check("One persisted payment attempt", 1, len(payments["attempts"]) if payments else None)
    check(
        "Signed net ledger amount",
        order["total_amount_minor"] if expected == "CONFIRMED" else 0,
        sum(e["amount_minor"] * (1 if e["kind"] == "DEBIT" else -1) for e in ledger)
        if ledger is not None
        else None,
    )
    if run["scenario"] in {"late", "refund"}:
        debits = [e for e in ledger if e["kind"] == "DEBIT"] if ledger is not None else None
        reversals = [e for e in ledger if e["kind"] == "REVERSAL"] if ledger is not None else None
        check(
            "Late debit absent or reversed exactly once for the same payment",
            True,
            len(debits) <= 1
            and len(reversals) == len(debits)
            and all(
                d.get("payment_id")
                and sum(r.get("payment_id") == d["payment_id"] for r in reversals) == 1
                for d in debits
            )
            if ledger is not None
            else None,
        )
    else:
        check(
            "Debit entry count",
            1 if expected == "CONFIRMED" else 0,
            sum(e["kind"] == "DEBIT" for e in ledger) if ledger is not None else None,
        )
    check(
        "Ledger currency and amount",
        True,
        all(
            e["currency"] == order["currency"] and e["amount_minor"] == order["total_amount_minor"]
            for e in ledger
        )
        if ledger is not None
        else None,
    )
    for line in order["lines"]:
        sku = line["sku"]
        before, after = run["baseline_stock"].get(sku), audit["stocks"].get(sku)
        delta = line["quantity"] if expected == "CONFIRMED" else 0
        check(
            "Stock conservation: " + sku,
            before["on_hand"] - delta if before else None,
            after["on_hand"] if after and before else None,
        )
        check(
            "Reserved stock restored: " + sku,
            before["reserved"] if before else None,
            after["reserved"] if after and before else None,
        )
        # reserve + commit/release/expiry each advance stock once; retries must not.
        check(
            "Exactly two stock transitions: " + sku,
            before["stock_version"] + 2 if before else None,
            after["stock_version"] if after and before else None,
        )
    publication = run.get("publication")
    check(
        "Exact active Gold identity/version/status/amount",
        True,
        publication["status"] == "visible"
        and publication["order_version"] == order["order_version"]
        if publication and publication["status"] != "unavailable"
        else None,
    )
    if run["scenario"] == "analytics":
        check(
            "Terminal order observed while worker paused and exact Gold pending",
            True,
            run.get("pending_proof") is True,
        )
        check("Worker resumed from retained container", True, run.get("recovered") is True)
    elif run["scenario"] == "retry":
        check(
            "Response suppressed after committed backend acknowledgement",
            True,
            run.get("response_lost") is True,
        )
        check(
            "Identical request/key/body returns original order", True, run.get("retry_same_order")
        )
    elif run["scenario"] == "crash":
        marker = run.get("checkpoint")
        check(
            "Acknowledged saga.after_commit process exit 86",
            True,
            marker["order_id"] == order["order_id"] and marker["exit_code"] == 86
            if marker
            else None,
        )
        check("Process restarted with retained state", True, run.get("recovered") is True)
    elif run["scenario"] == "decline":
        check(
            "Deterministic decline recorded",
            "DECLINED",
            payments["attempts"][0]["failure_code"] if payments and payments["attempts"] else None,
        )
    elif run["scenario"] == "late":
        check("Persisted 35-second payment delay", 35_000, run.get("payment_delay_ms"))
        gap = run.get("payment_due_after_expiry_ms")
        check(
            "Payment scheduled beyond reservation expiry",
            True,
            gap > 0 if gap is not None else None,
        )
        check("Reservation expiry observed before completion due", True, run.get("expiry_proof"))
        check("35-second completion deadline observed", True, run.get("late_due_observed"))
        check(
            "Expired payment callback quiesced",
            True,
            payments["quiesced"] and payments["attempts"][0]["status"] in {"CANCELLED", "REVERSED"}
            if payments and payments["attempts"]
            else None,
        )
    elif run["scenario"] == "refund":
        check("Debit observed before reversal", True, bool(run.get("debit_observed")))
        check(
            "Exactly one real debit and reversal",
            [1, 1],
            [sum(e["kind"] == kind for e in ledger) for kind in ("DEBIT", "REVERSAL")]
            if ledger is not None
            else None,
        )
        check(
            "Persisted payment reversed and quiesced",
            True,
            payments["quiesced"] and payments["attempts"][0]["status"] == "REVERSED"
            if payments and payments["attempts"]
            else None,
        )
    return checks
