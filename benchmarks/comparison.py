"""P9 paired comparisons from retained evidence, with no fastest-run selection."""

from statistics import median

from benchmarks.metrics import percent_change
from benchmarks.performance import load_performance_run
from benchmarks.planning import Trial, check_pair_controls
from projectctl.artifacts import content_hash, file_hash, write_json
from projectctl.config import InputError, repo_path
from projectctl.models import ExitCode
from projectctl.providers import DependencyError, ProviderResult

# Unknown metrics remain descriptive; their direction is never guessed.
DIRECTIONS = {
    "gold_goodput": "gain",
    "admitted_rate": "gain",
    "raw_rows_per_second": "gain",
    "canonical_rows_per_second": "gain",
    "import_total_seconds": "reduction",
    "producer_to_gold_p95_ms": "reduction",
    "schedule_to_gold_p95_ms": "reduction",
    "query_p95_ms": "reduction",
    "workflow_p95_ms": "reduction",
    "peak_memory_mib": "reduction",
    "mean_cpu_percent": "reduction",
    "file_opens": "reduction",
    "selected_file_bytes": "reduction",
    "actual_read_bytes": "reduction",
    "acceptance_p95_ms": "reduction",
    "finality_p95_ms": "reduction",
}


def metric_direction(name):
    """Directions for the exact names emitted by performance_metrics; unknowns stay null."""
    if name in DIRECTIONS:
        return DIRECTIONS[name]
    if name.endswith((".p50_seconds", ".p95_seconds", ".p99_seconds", ".cpu_percent")):
        return "reduction"
    if name.endswith(".peak") and any(
        f".{metric}." in name
        for metric in (
            "process_resident_memory_bytes",
            "container_memory_bytes",
            "kafka_consumer_lag",
            "gold_pending_events",
            "outbox_pending",
            "outbox_oldest_age_seconds",
        )
    ):
        return "reduction"
    return None


def spread(values):
    return {"median": median(values), "min": min(values), "max": max(values), "values": values}


def compare_metrics(baseline, candidate):
    """Pure arithmetic; callers must separately verify each raw evidence bundle."""
    left = [{m["name"]: m for m in run["metrics"]} for run in baseline]
    right = [{m["name"]: m for m in run["metrics"]} for run in candidate]
    names = sorted(set().union(*(set(group) for group in left + right)))
    results = []
    for name in names:
        rows = [group.get(name) for group in left + right]
        measured = all(
            r is not None
            and r["status"] == "MEASURED"
            and r["value"] is not None
            and r["sample_count"] > 0
            and r["timing_validity"] in {"VALID", "RECOVERY_UPPER_BOUND"}
            for r in rows
        )
        semantics = {
            (r["unit"], r["cohort"], r["quantile_method"], r["timing_validity"])
            for r in rows
            if r is not None
        }
        if len(semantics) > 1:
            raise InputError("paired metric units/cohort/quantiles/timing boundary differ")
        result = {
            "name": name,
            "status": "MEASURED" if measured else "INCOMPLETE",
            "baseline": None,
            "candidate": None,
            "improvement_percent": None,
            "direction": metric_direction(name),
            "unresolved_counts": [r["unresolved_count"] if r else None for r in rows],
            "sample_counts": [r["sample_count"] if r else 0 for r in rows],
            "semantics": list(next(iter(semantics))) if semantics else None,
            "absolute_change": None,
        }
        if measured:
            a, b = (
                spread([g[name]["value"] for g in left]),
                spread([g[name]["value"] for g in right]),
            )
            result.update(baseline=a, candidate=b, absolute_change=b["median"] - a["median"])
            if result["direction"]:
                result["improvement_percent"] = percent_change(
                    a["median"], b["median"], direction=result["direction"]
                )["value"]
        results.append(result)
    return results


def compare_runs(baseline_run_ids, candidate_run_ids):
    if len(baseline_run_ids) != 3 or len(candidate_run_ids) != 3:
        raise InputError("a comparison requires all three baseline and candidate repetitions")
    paths = baseline_run_ids + candidate_run_ids
    if len({repo_path(p) for p in paths}) != 6:
        raise InputError("all six run directories must be distinct")
    left, right = [
        [load_performance_run(repo_path(p)) for p in group]
        for group in (baseline_run_ids, candidate_run_ids)
    ]
    for group in (left, right):
        if {r["manifest"]["repetition"] for r in group} != {1, 2, 3}:
            raise InputError("repetitions 1,2,3 required without duplicates")
        group.sort(key=lambda r: r["manifest"]["repetition"])
    reference = left[0]

    def identity(run):
        return (
            run["manifest"]["git"],
            run["manifest"]["locks"],
            run["manifest"]["host"],
            run["manifest"]["workload_id"],
        )

    for group in (left, right):
        for run in group[1:]:
            first = group[0]
            if (
                run["config"] != first["config"]
                or run["manifest"]["variant_id"] != first["manifest"]["variant_id"]
                or any(
                    run["order"].get(k) != first["order"].get(k)
                    for k in ("fault", "series", "effective_parameters", "layout_child")
                )
            ):
                raise InputError("repetitions change treatment or frozen controls")
    for run in left + right:
        if identity(run) != identity(reference):
            raise InputError("comparison changes code/locks/actual hardware/workload")
        names = [m["name"] for m in run["summary"]["metrics"]]
        if len(names) != len(set(names)):
            raise DependencyError("duplicate summary metric identities")
        for metric in run["summary"]["metrics"]:
            if metric["status"] == "MEASURED":
                names = {ref["path"] for ref in run["manifest"]["artifacts"]}
                if metric["evidence_path"] not in names:
                    raise DependencyError("metric raw evidence is not indexed")
    for a, b in zip(left, right, strict=True):
        ma = a["manifest"]
        # A resumed member may have an older session ID; the stable trial key and
        # repetition/config controls are authoritative, not a newly generated UUID.
        ta, tb = [
            Trial(
                r["manifest"]["workload_id"],
                r["manifest"]["variant_id"],
                r["manifest"]["repetition"],
                r["order"]["fault"],
                r["config"],
                r["order"],
            )
            for r in (a, b)
        ]
        recovery = (
            ma["workload_id"] == "W-CHECKOUT"
            and ta.variant == tb.variant == "B0"
            and ta.fault == "none"
            and tb.fault in {"relay-publish-before-mark", "saga-after-stock-commit"}
        )
        check_pair_controls(
            ta,
            tb
            if not recovery
            else Trial(tb.workload, tb.variant, tb.repetition, ta.fault, tb.config, tb.order),
        )
        pa, pb = [r["order"]["effective_parameters"] for r in (a, b)]
        if ta.variant == tb.variant == "F-PARTITION":
            if (
                {pa["partitioning"], pb["partitioning"]} != {"unpartitioned", "date_type"}
                or {k: v for k, v in pa.items() if k != "partitioning"}
                != {k: v for k, v in pb.items() if k != "partitioning"}
                or pa["target_file_mib"] != 32
                or pa["file_layout"] != "compact"
            ):
                raise InputError("partition-only comparison must keep target/codec/rows fixed")
        elif ta.variant == tb.variant and not recovery:
            raise InputError("identical treatments are not an optimization comparison")
        if ma["workload_id"] == "W-IMPORT":
            from benchmarks.performance import read_json

            reports = [read_json(r["directory"] / "import_timings.json") for r in (a, b)]
            if not reports[0].get("logical_digest") or reports[0]["logical_digest"] != reports[
                1
            ].get("logical_digest"):
                raise InputError("I0/I1 canonical business digests differ or are unavailable")
    report = {
        "schema_version": 1,
        "status": "MEASURED",
        "workload": reference["manifest"]["workload_id"],
        "baseline_variant": left[0]["manifest"]["variant_id"],
        "candidate_variant": right[0]["manifest"]["variant_id"],
        "git": reference["manifest"]["git"],
        "metrics": compare_metrics([r["summary"] for r in left], [r["summary"] for r in right]),
        "runs": [
            {
                "path": r["directory"].relative_to(repo_path(".")).as_posix() + "/manifest.json",
                "sha256": file_hash(r["directory"] / "manifest.json"),
            }
            for r in left + right
        ],
        "selection": None,
        "limitations": [
            "Three repetitions are descriptive, not proof of statistical significance.",
            "Completed-only quantiles retain unresolved counts; no unconditional SLO claim.",
            "No winner is selected automatically; costs and interaction trials require review.",
        ],
    }
    if not report["metrics"] or any(m["status"] != "MEASURED" for m in report["metrics"]):
        report["status"] = "INCOMPLETE"
    report["content_sha256"] = content_hash(report)
    return report


def execute_comparison(invocation):
    from projectctl.artifacts import save_evidence

    args = invocation.arguments
    try:
        report = compare_runs(args["baseline"], args["candidate"])
        directory = repo_path(args["out"])
        directory.mkdir(parents=True, exist_ok=False)
        write_json(directory / "comparison.json", report)
        lines = [
            "# Paired performance comparison",
            "",
            f"Workload: {report['workload']}",
            "",
            "All three paired repetitions are retained. Values are median [min, max].",
            "",
            "| Metric | Unit/cohort/method/timing | Baseline | Candidate | Improvement % | "
            "Absolute change | Samples | Unresolved | Status |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for row in report["metrics"]:

            def cell(value):
                return (
                    "null"
                    if value is None
                    else f"{value['median']} [{value['min']}, {value['max']}]"
                )

            lines.append(
                f"| {row['name']} | {row['semantics']} | {cell(row['baseline'])} | "
                f"{cell(row['candidate'])} | {row['improvement_percent']} | "
                f"{row['absolute_change']} | {row['sample_counts']} | "
                f"{row['unresolved_counts']} | {row['status']} |"
            )
        lines.extend(["", *["- " + item for item in report["limitations"]]])
        (directory / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = ProviderResult(
            ExitCode.COMPLETED if report["status"] == "MEASURED" else ExitCode.DEPENDENCY_FAILURE,
            (args["out"] + "/comparison.json",),
            "offline",
        )
    except (DependencyError, OSError, ValueError, KeyError, TypeError) as exc:
        if isinstance(exc, InputError):
            raise
        result = ProviderResult(
            ExitCode.DEPENDENCY_FAILURE,
            (
                str(exc)
                if isinstance(exc, DependencyError)
                else "comparison evidence unavailable or invalid",
            ),
            "offline",
        )
    return save_evidence(invocation, result)
