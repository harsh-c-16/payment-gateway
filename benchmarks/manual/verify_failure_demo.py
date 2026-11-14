"""Real local-service rehearsal. Explicit CLI flag authorizes simulated purchases."""

import argparse
import json
import time
from pathlib import Path

from benchmarks.failure_demo.controller import SCENARIOS, Controller, Selection
from benchmarks.failure_demo.runtime import Runtime


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulate-purchases", action="store_true", required=True)
    parser.add_argument("--scenario", choices=["all", *SCENARIOS], default="all")
    parser.add_argument("--out", type=Path, default=Path("artifacts/failure-demo-live"))
    args = parser.parse_args()
    controller = Controller(Runtime(), args.out)
    results = []
    try:
        deadline = time.monotonic() + 40
        while not all(
            controller.runtime.health(role) is True
            for role in ("store", "orders", "inventory", "payments", "analytics")
        ):
            if time.monotonic() >= deadline:
                raise RuntimeError("Real service readiness was not established in 40 seconds")
            time.sleep(0.5)
        for scenario in SCENARIOS if args.scenario == "all" else [args.scenario]:
            run = controller.prepare(Selection(scenario=scenario, mode="automated"))["run"]
            controller.automate(run["id"])
            current = controller.snapshot()["run"]
            result = {
                "scenario": scenario,
                "run_id": current["id"],
                "status": current["status"],
                "order_id": current["order_id"],
                "checks": current["checks"],
                "message": current["message"],
            }
            results.append(result)
            (args.out / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
            print(scenario, current["status"], current["order_id"], flush=True)
            if current["status"] != "Passed":
                print(current["message"], flush=True)
                return 1
        return 0
    finally:
        controller.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
