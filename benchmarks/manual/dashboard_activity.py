"""Generate bounded real demo activity, then verify its active Gold membership.

Run after start-prototype.ps1. Fixed chat uses no generative calls. An optional
single simulated checkout requires --simulate-purchases. No fake metrics, direct
Kafka sends, data resets or automatic retries of mutating requests are used.
"""

import argparse
import json
import time
from pathlib import Path
from uuid import uuid4

import httpx

from infra import postgres

ORIGIN = "http://127.0.0.1:8001"
HELPER = "http://127.0.0.1:8010"
QUERIES = (
    "shirts under 1000 rupees",
    "watches under 1000 rupees",
    "shoes under 1500 rupees",
)


def generate(out, turns=6, interval=2, simulate_purchases=False):
    out.mkdir(parents=True, exist_ok=False)
    context = json.loads(
        (postgres.ROOT / "artifacts/infra/prototype-local/context.json").read_text()
    )
    identity = {
        "namespace": context["RUN_NAMESPACE"],
        "user_id": "dashboard-demo-" + uuid4().hex[:12],
        "run_id": str(uuid4()),
        "correlation_id": str(uuid4()),
    }
    result = {
        "status": "RUNNING",
        "scope": "Real local demonstration activity; not a performance benchmark",
        "identity": identity,
        "turns": [],
        "purchase": None,
    }

    def save():
        (out / "activity.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    with httpx.Client(timeout=45, trust_env=False, follow_redirects=False) as client:

        def helper(path, body=None):
            response = client.request(
                "GET" if body is None else "POST",
                HELPER + path,
                headers={"Origin": ORIGIN},
                json=body,
            )
            response.raise_for_status()
            return response.json()

        def store(path, body, request_id=None):
            request_id = request_id or str(uuid4())
            headers = {
                "X-" + key.replace("_", "-"): value for key, value in identity.items()
            }
            headers.update({"X-Request-ID": request_id, "Idempotency-Key": str(uuid4())})
            response = client.post(ORIGIN + path, headers=headers, json=body)
            response.raise_for_status()
            return response.json()

        try:
            state = helper("/state")
            if state["namespace"] != identity["namespace"]:
                raise RuntimeError("Helper and store namespaces differ")
            session = store("/v1/sessions", {})
            identity["session_id"] = session["session_id"]
            result["cart_id"] = session["cart_id"]
            save()
            for i in range(turns):
                query, request_id = QUERIES[i % len(QUERIES)], str(uuid4())
                turn = store(
                    f"/v1/sessions/{session['session_id']}/shopping-turns",
                    {"text": query, "mode": "fixed", "request_id": request_id},
                    request_id,
                )
                result["turns"].append({"query": query, "response": turn})
                save()
                if turn["outcome"] != "success" or turn["llm_call_count"] != 0:
                    raise RuntimeError("A fixed search failed; inspect the retained response")
                print(f"Search {i + 1}/{turns}: {len(turn['products'])} products", flush=True)
                if i + 1 < turns:
                    time.sleep(interval)

            # Observe the actual event IDs for each search in queryable active Gold.
            for i, turn in enumerate(result["turns"]):
                search_id = turn["response"]["search_id"]
                deadline = time.monotonic() + 60
                while True:
                    trace = helper(f"/journey/trace?kind=search&id={search_id}")
                    visibility = trace.get("visibility") or {}
                    turn["trace"] = trace
                    ids = {e["event_id"] for e in trace["events"]}
                    if (
                        ids
                        and visibility.get("queryable") is True
                        and ids <= set(visibility.get("visible_event_ids", []))
                    ):
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Search events did not reach active Gold in 60 seconds")
                    time.sleep(2)
                save()
                print(f"Search {i + 1}: {len(ids)} exact events visible in Gold", flush=True)

            if simulate_purchases:
                # Use the same consent-gated controller and independent verifier as the UI.
                prepared = helper("/prepare", {"scenario": "purchase", "mode": "automated"})
                run_id = prepared["run"]["id"]
                result["purchase"] = {"run_id": run_id, "status": "PREPARED"}
                save()
                helper(f"/runs/{run_id}/test", {"confirmed": True})
                deadline = time.monotonic() + 260
                while True:
                    run = helper("/state")["run"]
                    if run["id"] != run_id:
                        raise RuntimeError("Current controller run changed")
                    result["purchase"] = run
                    save()
                    if not run.get("test_running") and run["status"] != "Pending":
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Purchase observation timed out; inspect the dashboard")
                    time.sleep(2)
                if run["status"] != "Passed" or not run["checks"] or any(
                    c["passed"] is not True for c in run["checks"]
                ):
                    raise RuntimeError("Simulated purchase did not reconcile; evidence retained")
                print(f"One simulated checkout reconciled: {run['order_id']}", flush=True)
            result["infrastructure"] = helper("/infrastructure")
            result["status"] = "PASS"
            save()
            print(f"Dashboard activity ready. Evidence: {out}", flush=True)
        except Exception as exc:
            result["status"] = "INCOMPLETE"
            result["error_type"] = type(exc).__name__
            save()
            raise
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--turns", type=int, choices=range(1, 31), default=6)
    parser.add_argument("--interval-seconds", type=float, default=2)
    parser.add_argument("--simulate-purchases", action="store_true")
    parser.add_argument(
        "--out", type=Path, default=Path("artifacts/dashboard-activity") / uuid4().hex
    )
    args = parser.parse_args()
    if not 1 <= args.interval_seconds <= 30:
        parser.error("--interval-seconds must be between 1 and 30")
    generate(args.out, args.turns, args.interval_seconds, args.simulate_purchases)


if __name__ == "__main__":
    main()
