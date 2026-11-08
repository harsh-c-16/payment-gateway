"""Opt-in M3 route probes with explicit ASGI/SQL doubles; never live acceptance.

These consumer probes retain failures without adding expected failures or editing
the transaction owner's tests. ASGI lifespan is not started, so no saga/expiry
worker or real database, broker, payment or network operation runs.
"""

import argparse
import asyncio
import importlib
import os
from contextlib import ExitStack, contextmanager
from unittest.mock import patch
from uuid import uuid4

import httpx

from projectctl.artifacts import write_json
from projectctl.config import repo_path


class DatabaseDouble:
    @contextmanager
    def transaction(self, **kwargs):
        yield self

    def execute(self, *args, **kwargs):
        return self

    def fetchall(self):
        return [{"synthetic_audit_row": True, "kind": "DEBIT", "amount_minor": 0}]


class EventsDouble:
    mode = "stub"


async def probe(
    service,
    path,
    *,
    namespace="bench-boundary-probe",
    body=None,
    benchmark=True,
    fault_injection=False,
):
    module = importlib.import_module("services." + service + ".app")
    order_id = str(uuid4())
    with ExitStack() as patches:
        patches.enter_context(
            patch.dict(
                os.environ,
                {
                    "INTERNAL_API_TOKEN": "explicit-synthetic-token",
                    "BENCHMARK_MODE": str(benchmark).lower(),
                    "FAULT_INJECTION_ENABLED": str(fault_injection).lower(),
                },
            )
        )
        if "{order_id}" in path:
            patches.enter_context(
                patch.object(
                    module.commands,
                    "get_order_snapshot",
                    return_value={
                        "order_id": order_id,
                        "user_id": "original-owner",
                        "status": "CONFIRMED",
                        "order_version": 1,
                    },
                )
            )
        app = module.create_app(db=DatabaseDouble(), events=EventsDouble())
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://explicit-asgi-double"
        ) as client:
            headers = {
                "X-Namespace": namespace,
                "X-Run-ID": "explicit-boundary-double",
                "X-User-ID": "another-user",
                "X-Correlation-ID": "boundary-double",
                "X-Request-ID": str(uuid4()),
            }
            # A missing-token rejection must not hide a broken fault-scope guard.
            if body is not None:
                headers["Authorization"] = "Bearer explicit-synthetic-token"
            response = await client.request(
                "GET" if body is None else "POST",
                path.format(order_id=order_id),
                headers=headers,
                json=body,
            )
    expected = {403} if body is not None else ({403, 404} if "{order_id}" in path else {401, 403})
    return {
        "service": service,
        "path": path,
        "namespace": namespace,
        "benchmark_mode": benchmark,
        "fault_injection_enabled": fault_injection,
        "service_token_supplied": body is not None,
        "test_mode": "stub",
        "assertions": [
            {
                "name": "reject_cross_principal_or_unapproved_internal_access",
                "expected": sorted(expected),
                "observed": response.status_code,
                "passed": response.status_code in expected,
            }
        ],
        "synthetic_response": response.text,
    }


async def verify():
    # Sequential: each real app construction has its own explicit environment patches.
    cases = []
    for service, path in (
        ("orders", "/v1/orders/{order_id}"),
        ("orders", "/v1/orders/{order_id}/events"),
        ("orders", "/internal/v1/audit/orders"),
        ("inventory", "/internal/v1/audit/stock"),
        ("payments", "/internal/v1/audit/ledger"),
    ):
        cases.append(await probe(service, path))
    for namespace, benchmark, fault_injection in (
        ("bench-boundary-probe", True, False),
        ("bench-boundary-probe", False, True),
        ("dev", True, True),
    ):
        cases.append(
            await probe(
                "orders",
                "/internal/v1/fault-barriers",
                namespace=namespace,
                body={"barrier_name": "explicit-boundary-double", "enabled": True},
                benchmark=benchmark,
                fault_injection=fault_injection,
            )
        )
    return {
        "test_mode": "stub",
        "real_integration": "NOT_RUN",
        "cases": cases,
        "passed": all(a["passed"] for case in cases for a in case["assertions"]),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    directory = repo_path(args.out)
    if not directory.is_relative_to(repo_path("artifacts")):
        parser.error("--out must be a fresh directory under artifacts/")
    directory.mkdir(parents=True, exist_ok=False)
    result = asyncio.run(verify())
    write_json(directory / "boundaries.json", result)
    failed = sum(not a["passed"] for case in result["cases"] for a in case["assertions"])
    print(f"Explicit ASGI/SQL doubles: {failed} failed boundary probes; real integration NOT_RUN")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
