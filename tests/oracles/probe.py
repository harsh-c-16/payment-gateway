"""Save manually inspectable P3 oracle and tiny-math evidence; no live providers."""

import argparse
import json
from pathlib import Path

from benchmarks.dataset_checks import inspect_source
from benchmarks.metrics import kafka_lag, latency_summary, percent_change
from benchmarks.reconciliation import reconcile_run

from .doubles import CORRUPTIONS, clean_evidence, corrupt_evidence

ROOT = Path(__file__).resolve().parents[2]


def save(target, document):
    with target.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    expected, observed = clean_evidence()
    clean = reconcile_run(expected, observed)
    assert clean["reconciliation"]["passed"]
    save(
        args.out / "oracle_clean.json",
        {"test_mode": "stub", "expected": expected, "observed": observed, "result": clean},
    )
    checks = []
    for name, reason in CORRUPTIONS.items():
        corrupted = corrupt_evidence(name, observed)
        result = reconcile_run(expected, corrupted)
        detected = not result["reconciliation"]["passed"] and any(
            item.split(":")[0] == reason for item in result["reconciliation"]["invariant_failures"]
        )
        checks.append(
            {
                "case_id": name,
                "test_mode": "stub",
                "expected_reason": reason,
                "detected_for_intended_reason": detected,
                "corrupt_observation": corrupted,
                "result": result,
            }
        )
    save(args.out / "oracle_corruptions.json", checks)
    assert all(row["detected_for_intended_reason"] for row in checks)
    tiny = {
        "test_mode": "offline",
        "purpose": "hand-computed math checks, not SUT measurements",
        "durations_ms": [10, 20, 30, 40, 100],
        "latency": latency_summary([10, 20, 30, 40, 100], expected_count=5),
        "kafka_lag": kafka_lag(25, 20),
        "latency_reduction": percent_change(100, 80, direction="reduction"),
        "throughput_gain": percent_change(100, 125, direction="gain"),
        "no_timing": latency_summary([], expected_count=1),
    }
    assert tiny["latency"]["completed_only"] == {"p50": 30, "p95": 100, "p99": 100}
    assert (
        tiny["kafka_lag"] == 5
        and tiny["latency_reduction"]["value"] == 20
        and tiny["throughput_gain"]["value"] == 25
    )
    assert tiny["no_timing"]["complete_cohort_p99"] is None
    save(args.out / "tiny_math.json", tiny)
    source = inspect_source(ROOT / "data/raw/flipkart_com-ecommerce_sample.csv")
    save(args.out / "dataset_checks.json", source)
    if source["status"] not in {"PASS", "NOT_RUN"}:
        raise AssertionError("available exact dataset did not pass its independent checks")
    dirty = json.loads(
        (ROOT / "contracts/fixtures/catalog/dirty_catalogue.json").read_text(encoding="utf-8")
    )
    save(
        args.out / "fixture_review.json",
        {
            "synthetic": True,
            "provider_normalization_comparison": "NOT_RUN",
            "cases": [
                row
                for row in dirty["cases"]
                if row["case_id"]
                in {
                    "ordinary-price",
                    "retail-is-not-sale-fallback",
                    "duplicate-pid-latest",
                    "absent-size-colour-material",
                }
            ],
        },
    )
    assistant = json.loads(
        (ROOT / "contracts/fixtures/assistant/scenarios.json").read_text(encoding="utf-8")
    )
    groups = {}
    for scenario in assistant["scenarios"]:
        groups.setdefault(scenario["group"], scenario)
    save(
        args.out / "assistant_review_samples.json",
        {
            "review_status": "awaiting_human_review",
            "samples": list(groups.values()),
            "labels_frozen": False,
            "real_quality": "NOT_RUN",
        },
    )
    print(
        json.dumps(
            {
                "oracle_corruptions_detected": len(checks),
                "source_check": source["status"],
                "tiny_math": "PASS",
                "human_label_review": "PENDING",
                "real_integration": "NOT_RUN",
            }
        )
    )


if __name__ == "__main__":
    main()
