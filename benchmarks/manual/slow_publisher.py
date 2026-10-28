"""P4 slow-publisher demonstration using an explicitly imported TEST double.

No Kafka/API/service is started. This is a two-second smoke/test experiment,
never a steady-state performance result. Run from the repository root.
"""

import argparse
import asyncio
import json
from uuid import uuid4

from benchmarks.experiment import run_experiment
from projectctl.artifacts import write_json
from projectctl.config import ROOT, load_config, repo_path
from tests.benchmarks.doubles import LifecycleDouble, SlowPublisher


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="artifacts/p4/slow-" + str(uuid4()))
    args = parser.parse_args(argv)
    repo_path(args.out)
    config = load_config()
    config.artifacts.root = args.out
    config.generator.key_count = 2
    config.generator.concurrency = 1
    config.generator.queue_limit = 4
    config.workloads["W-PIPE"].rate_per_second = 200.0
    explicit_double = LifecycleDouble(SlowPublisher(delay=0.05))
    manifest = asyncio.run(
        run_experiment(
            "W-PIPE",
            "B0",
            1,
            42,
            config=config,
            bindings=explicit_double.bindings(),
            duration_seconds=2,
            warmup_seconds=1,
            evidence_kind="smoke",
        )
    )
    directory = repo_path(args.out) / manifest["run_id"]
    admission = json.loads((directory / "admission.json").read_text(encoding="utf-8"))
    generator = json.loads((directory / "generator.json").read_text(encoding="utf-8"))
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    measured = admission["phases"]["measurement"]
    checks = {
        "planned_measurement_count_is_400": measured["planned"] == 400,
        "target_miss_is_visible": summary["exit_code"] == 5 and measured["missed"] > 0,
        "offered_rate_stays_200": summary["metrics"][0]["value"] == 200,
        "pending_count_bounded": generator["peak_pending_count"] <= 4,
        "pending_bytes_bounded": generator["peak_pending_bytes"] <= 67108864,
        "every_planned_record_has_outcome": admission["expected_count"]
        == admission["observed_count"],
        "mode_is_explicit_stub": summary["test_mode"] == "stub",
    }
    write_json(directory / "demo_checks.json", checks)
    print(
        json.dumps(
            {
                "evidence_dir": directory.relative_to(ROOT).as_posix(),
                "measurement": measured,
                "checks": checks,
                "SUT_performance": "NOT_RUN",
                "experiment_exit": summary["exit_code"],
            }
        )
    )
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    # Script execution needs the repo import root just like the older verifiers.
    raise SystemExit(main())
