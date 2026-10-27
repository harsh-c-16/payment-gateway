"""Derive P9 summary rows from raw P4/P5 evidence rather than provider target values."""

from benchmarks.observation_summary import rebuild
from benchmarks.performance import STREAM_WORKLOADS, read_json
from projectctl.artifacts import content_hash
from projectctl.models import Metric


def derive_metrics(directory, config, run_id, workload, existing):
    telemetry = rebuild(directory)
    admission = read_json(directory / "admission.json")["phases"]["measurement"]
    cohort = {"finite": "finite_job", "sustained": "measurement", "queries": "query"}[
        config.workloads[workload].kind
    ]
    result = [m for m in existing if m.name != "gold_goodput"]

    def add(name, unit, value, count, evidence, *, quantile=None, unresolved=None, valid=True):
        result.append(
            Metric(
                name=name,
                unit=unit,
                value=value,
                sample_count=count if value is not None else 0,
                numerator=None,
                denominator=None,
                cohort=cohort,
                quantile_method=quantile,
                unresolved_count=admission["unresolved"] if unresolved is None else unresolved,
                timing_validity="VALID" if value is not None and valid else "MISSING",
                run_id=run_id,
                config_sha256=content_hash(config.model_dump()),
                status="MEASURED" if value is not None and count and valid else "INCOMPLETE",
                evidence_path=evidence,
            )
        )

    rates = telemetry["rates"]
    if workload in STREAM_WORKLOADS:
        add(
            "gold_goodput",
            "events/second",
            rates["gold_goodput"],
            admission["planned"],
            "gold_visibility.jsonl",
        )
    for row in telemetry["series"]:
        prefix = row["component"] + "." + row["metric"]
        # Series labels distinguish partitions/services sharing one metric name.
        suffix = content_hash({"labels": row["labels"]})[:12]
        add(
            prefix + "." + suffix + ".peak",
            row["unit"],
            row["peak"],
            row["sample_count"],
            "observations.jsonl",
        )
        if "mean_cpu_percent" in row:
            add(
                prefix + "." + suffix + ".cpu_percent",
                "percent",
                row["mean_cpu_percent"],
                len(row["cpu_percent_samples"]),
                "observations.jsonl",
            )
    # Keep stage-specific distributions separate; missing cohort visibility is
    # carried beside the completed-only quantiles in the raw telemetry summary.
    for row in telemetry["latencies"]:
        if row["phase"] != "measurement":
            continue
        for q in ("p50", "p95", "p99"):
            add(
                f"{row['component']}.{row['stage']}.{q}_seconds",
                "seconds",
                row["completed_only"][q],
                row.get("sample_count", 0),
                "timings.jsonl",
                quantile="nearest-rank",
                valid=row.get("timing_validity", "VALID") == "VALID",
            )
        aliases = {
            "producer_to_gold": "producer_to_gold_p95_ms",
            "schedule_to_gold": "schedule_to_gold_p95_ms",
            "query": "query_p95_ms",
            "workflow": "workflow_p95_ms",
            "acceptance": "acceptance_p95_ms",
            "finality": "finality_p95_ms",
        }
        if (
            row["stage"] in aliases
            and sum(
                r["phase"] == "measurement" and r["stage"] == row["stage"]
                for r in telemetry["latencies"]
            )
            == 1
        ):
            value = row["completed_only"]["p95"]
            add(
                aliases[row["stage"]],
                "milliseconds",
                value * 1000 if value is not None else None,
                row["sample_count"],
                "timings.jsonl",
                quantile="nearest-rank",
                valid=row.get("timing_validity", "VALID") == "VALID",
            )
    if workload == "W-IMPORT":
        report = read_json(directory / "import_timings.json")
        seconds = report["raw_to_ready_seconds"]
        if type(seconds) not in {float, int} or seconds <= 0:
            raise ValueError("finite raw-to-ready elapsed time required")
        add("import_total_seconds", "seconds", seconds, 1, "import_timings.json")
        add("raw_rows_per_second", "rows/second", 20000 / seconds, 20000, "import_timings.json")
        stage = report["stages"]["staging_seconds"]
        if type(stage) not in {float, int} or stage <= 0:
            raise ValueError("finite staging elapsed time required")
        add("canonical_rows_per_second", "rows/second", 19998 / stage, 19998, "import_timings.json")
    return result
