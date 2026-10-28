"""Capacity qualification from complete one-second measurement samples (P9)."""

import math
from datetime import datetime


def qualify_repetition(
    *,
    rate,
    planned,
    admitted,
    unresolved,
    unexpected_effects,
    samples,
    resources_within_budget,
    slo_met,
    generator_valid,
):
    """Samples cover measurement seconds 0..599; no missing values become zero."""
    if (
        type(rate) not in {int, float}
        or not math.isfinite(rate)
        or rate <= 0
        or any(
            type(n) is not int or n < 0 for n in (planned, admitted, unresolved, unexpected_effects)
        )
    ):
        raise ValueError("finite positive rate and nonnegative integer counts required")
    complete = (
        len(samples) == 600
        and [s.get("second") for s in samples] == list(range(600))
        and all(
            type(s.get(key)) in {float, int} and math.isfinite(s[key]) and s[key] >= 0
            for s in samples
            for key in ("lag", "pending_export", "outbox")
        )
    )
    reasons, slopes = [], {}
    if not complete:
        reasons.append("missing/invalid one-second measurement samples")
    else:
        tail = samples[-300:]
        for key in ("lag", "pending_export", "outbox"):
            center = sum(s[key] for s in tail) / 300
            slopes[key] = sum((i - 149.5) * (s[key] - center) for i, s in enumerate(tail)) / sum(
                (i - 149.5) ** 2 for i in range(300)
            )
        if slopes["lag"] > 1 or samples[-1]["lag"] > max(100, 2 * rate):
            reasons.append("lag slope/end exceeds sustainable bounds")
        if any(slopes[key] > 0 for key in ("pending_export", "outbox")):
            reasons.append("pending-export/outbox backlog is rising")
    if planned != rate * 600 or admitted < 0.99 * planned or admitted > planned:
        reasons.append("planned/admitted load fails the declared 99% tier")
    if unresolved or unexpected_effects:
        reasons.append("unresolved cohort or unexpected loss/duplicate/business effects")
    if resources_within_budget is not True:
        reasons.append("resource budget/OOM evidence invalid")
    if generator_valid is not True:
        reasons.append("generator saturation/lateness evidence invalid")
    return {
        "status": "MEASURED" if complete else "INCOMPLETE",
        "rate": rate,
        "capacity_valid": not reasons,
        "slo_met": slo_met if type(slo_met) is bool else None,
        "sustainable_with_slo": not reasons and slo_met is True,
        "capacity_without_slo": not reasons and slo_met is False,
        "slopes_per_second": slopes,
        "reasons": reasons,
    }


def qualify_tier(repetitions):
    if len(repetitions) != 3 or len({r["rate"] for r in repetitions}) != 1:
        raise ValueError("three repetitions of the same tested tier required")
    return {
        "rate": repetitions[0]["rate"],
        "capacity_valid": all(r["capacity_valid"] for r in repetitions),
        "sustainable_with_slo": all(r["sustainable_with_slo"] for r in repetitions),
        "repetitions": repetitions,
    }


def assess_run(directory, rate):
    """Project real raw observations onto the measurement window using the host UTC clock."""
    import json
    from collections import defaultdict

    from benchmarks.performance import load_performance_run, read_json

    run = load_performance_run(directory)
    generator = read_json(directory / "generator.json")
    counts = read_json(directory / "admission.json")["phases"]["measurement"]
    start = (
        datetime.fromisoformat(generator["wall_anchor"]).timestamp()
        + generator["measurement_start_elapsed_seconds"]
    )
    rows = [
        json.loads(line)
        for line in (directory / "observations.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    kinds = {
        "kafka_consumer_lag": "lag",
        "gold_pending_events": "pending_export",
        "outbox_pending": "outbox",
    }
    expected = {
        name: {row["series_key"] for row in rows if row["metric_name"] == metric}
        for metric, name in kinds.items()
    }
    values = defaultdict(dict)
    resources_valid = True
    memory_seconds = defaultdict(set)
    for row in rows:
        second = math.floor(datetime.fromisoformat(row["timestamp"]).timestamp() - start)
        if not 0 <= second < 600:
            continue
        name = kinds.get(row["metric_name"])
        if name:
            key = (second, name)
            if row["series_key"] in values[key] or row["status"] != "MEASURED":
                raise ValueError("duplicate/missing capacity observation within a second")
            values[key][row["series_key"]] = row["value"]
        if row["metric_name"] in {"cgroup_memory_current_bytes", "cgroup_memory_peak_bytes"}:
            memory_seconds[row["component"]].add(second)
            allocation = run["config"].profile.service_allocations.get(row["component"])
            if (
                allocation is None
                or row["status"] != "MEASURED"
                or row["value"] > allocation.memory_mib * 1024**2
                or row["details"].get("oom_kill_count") != 0
            ):
                resources_valid = False
    if set(memory_seconds) != set(run["config"].profile.services) or any(
        seconds != set(range(600)) for seconds in memory_seconds.values()
    ):
        resources_valid = False
    samples = []
    for second in range(600):
        if all(
            expected[name] and set(values[second, name]) == expected[name]
            for name in kinds.values()
        ):
            samples.append(
                {"second": second}
                | {name: sum(values[second, name].values()) for name in kinds.values()}
            )
    metrics = run["summary"]["metrics"]
    p95 = next((m for m in metrics if m["name"] == "producer_to_gold_p95_ms"), None)
    slo = p95["value"] <= 1000 if p95 and p95["status"] == "MEASURED" else None
    # Scheduling misses/unknowns are generator saturation, even if a sink is fast.
    generator_valid = counts["missed"] == counts["unresolved"] == 0
    return qualify_repetition(
        rate=rate,
        planned=counts["planned"],
        admitted=counts["acknowledged_in_window"],
        unresolved=counts["unresolved"],
        unexpected_effects=0,
        samples=samples,
        resources_within_budget=resources_valid,
        slo_met=slo,
        generator_valid=generator_valid,
    )
