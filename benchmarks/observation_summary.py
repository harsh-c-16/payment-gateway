"""Rebuild offline telemetry tables from immutable evidence, without Grafana."""

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean

from benchmarks.metrics import latency_summary
from projectctl.artifacts import content_hash, file_hash, write_json


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def lines(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def rebuild(directory):
    directory = Path(directory).resolve()
    manifest = load(directory / "telemetry_manifest.json")
    if manifest["content_sha256"] != content_hash(manifest):
        raise ValueError("telemetry manifest hash mismatch")
    for ref in manifest["artifacts"]:
        path = (directory / ref["path"]).resolve()
        if not path.is_relative_to(directory) or file_hash(path) != ref["sha256"]:
            raise ValueError("telemetry artifact hash mismatch")
    context = load(directory / "observation_context.json")
    expected = {s["key"]: s for c in context["collectors"] for s in c["series"]}
    grouped = {key: [] for key in expected}
    seen = set()
    for row in lines(directory / "observations.jsonl"):
        key = row["series_key"]
        if key not in expected or (key, row["sequence"]) in seen:
            raise ValueError("unexpected or duplicate observation series/tick")
        if any(
            row[key] != context[other]
            for key, other in (
                ("run_id", "run_id"),
                ("namespace", "namespace"),
                ("variant", "variant"),
                ("workload", "workload"),
                ("test_mode", "mode"),
            )
        ):
            raise ValueError("observation context mismatch")
        seen.add((key, row["sequence"]))
        grouped[key].append(row)
    highest = max((row["sequence"] for rows in grouped.values() for row in rows), default=-1)
    if context["duration_seconds"] is not None:
        import math

        expected_ticks = math.ceil(context["duration_seconds"] / context["interval_seconds"])
    else:
        import math

        end = load(directory / "observation_end.json")
        expected_ticks = math.ceil(end["stop_elapsed_seconds"] / context["interval_seconds"])
    summaries = []
    for key, spec in expected.items():
        rows = sorted(grouped[key], key=lambda r: r["sequence"])
        valid = [r["value"] for r in rows if r["status"] == "MEASURED"]
        missing = max(expected_ticks, highest + 1) - len(valid)
        entry = spec | {
            "sample_count": len(valid),
            "missing_samples": missing,
            "peak": max(valid) if valid else None,
            "mean": mean(valid) if valid else None,
            "end": rows[-1]["value"]
            if rows and rows[-1]["sequence"] == expected_ticks - 1
            else None,
            "status": "MEASURED" if valid and missing == 0 else "INCOMPLETE",
        }
        if spec["metric"] == "process_cpu_seconds_total":
            cpu = []
            for before, after in zip(rows, rows[1:], strict=False):
                if (
                    after["sequence"] != before["sequence"] + 1
                    or before["status"] != "MEASURED"
                    or after["status"] != "MEASURED"
                ):
                    continue
                elapsed = after["details"].get(
                    "sample_monotonic", after["observed_elapsed_seconds"]
                ) - before["details"].get("sample_monotonic", before["observed_elapsed_seconds"])
                cores = after["details"].get("allocated_cores")
                previous_cores = before["details"].get("allocated_cores")
                delta = after["value"] - before["value"]
                if cores and cores == previous_cores and elapsed > 0 and delta >= 0:
                    cpu.append(100 * delta / (elapsed * cores))
            entry["cpu_percent_samples"] = cpu
            entry["mean_cpu_percent"] = mean(cpu) if cpu else None
            entry["cpu_missing_intervals"] = max(0, expected_ticks - 1) - len(cpu)
            entry["cpu_status"] = (
                "MEASURED"
                if cpu and missing == 0 and not entry["cpu_missing_intervals"]
                else "INCOMPLETE"
            )
        summaries.append(entry)
    timings = defaultdict(list)
    for row in lines(directory / "timings.jsonl"):
        timings[(row["component"], row["stage"], row["phase"])].append(row["duration_seconds"])
    latency = [
        {
            "component": c,
            "stage": s,
            "phase": p,
            **latency_summary(values, expected_count=len(values)),
        }
        for (c, s, p), values in sorted(timings.items())
    ]
    return {
        "schema_version": 1,
        "context": context,
        "series": summaries,
        "latencies": latency,
        "status": "MEASURED"
        if summaries and all(s["status"] == "MEASURED" for s in summaries)
        else "INCOMPLETE",
        "rates": rates(directory, context=context, series=summaries),
        "limitations": [
            "Stub/test observations are not SUT performance results.",
            "CPU percentages require adjacent valid readings and declared allocated cores.",
            "RSS peaks are sampled; cgroup peaks have different accounting.",
            "Gold visibility polling is a conservative upper bound; timing gaps remain visible.",
            "Timing quantiles describe retained rows; business reconciliation is separate.",
        ],
    }


def rates(directory, *, context, series):
    result = {name: None for name in ("offered_rate", "admitted_rate", "gold_goodput")}
    required = [
        directory / name for name in ("generator.json", "admission.json", "emissions.jsonl")
    ]
    if not all(p.exists() for p in required):
        return result | {"status": "NOT_RUN"}
    generator, admission = load(required[0]), load(required[1])
    denominator = generator["window_seconds"] or generator["measured_job_seconds"]
    if not denominator or denominator <= 0:
        return result | {"status": "INCOMPLETE"}
    count = admission["phases"]["measurement"]
    result.update(
        offered_rate=count["planned"] / denominator,
        admitted_rate=count["acknowledged_in_window"] / denominator,
    )
    # Gold goodput needs a sustained measurement cohort and same-host UTC anchors.
    gold_series = [s for s in series if s["metric"] == "active_gold_members"]
    if (
        generator["window_seconds"]
        and context["shared_host_clock"]
        and gold_series
        and all(s["status"] == "MEASURED" for s in gold_series)
        and (directory / "gold_visibility.jsonl").exists()
    ):
        cohort = {
            r["event_or_request_id"]
            for r in lines(required[2])
            if r["phase"] == "measurement" and r["expected_disposition"] == "new_valid"
        }
        anchor = datetime.fromisoformat(generator["wall_anchor"])
        start = generator["measurement_start_elapsed_seconds"]
        visible = {
            r["event_id"]
            for r in lines(directory / "gold_visibility.jsonl")
            if r["event_id"] in cohort
            and start
            <= (datetime.fromisoformat(r["gold_visible_observed_at"]) - anchor).total_seconds()
            < start + denominator
        }
        result["gold_goodput"] = len(visible) / denominator
    return result | {
        "status": "MEASURED" if result["gold_goodput"] is not None else "INCOMPLETE",
        "unresolved": count["unresolved"],
        "missed": count["missed"],
        "denominator_seconds": denominator,
    }


def markdown(summary):
    context = summary["context"]
    rows = [
        f"# Telemetry: {context['run_id']}",
        "",
        f"Workload `{context['workload']}`; variant `{context['variant']}`; "
        f"mode **{context['mode']}**; evidence **{context['evidence_kind']}**; "
        f"status **{summary['status']}**.",
        "",
        "| Component / metric | Unit | Samples | Missing | Peak | End | Status |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for s in summary["series"]:
        values = [
            s["component"] + " / " + s["metric"],
            s["unit"],
            s["sample_count"],
            s["missing_samples"],
            s["peak"],
            s["end"],
            s["status"],
        ]
        rows.append(
            "| "
            + " | ".join("null" if v is None else str(v).replace("|", "\\|") for v in values)
            + " |"
        )
    rows.extend(["", "Rates: `" + json.dumps(summary["rates"], sort_keys=True) + "`", ""])
    rows.extend("- " + limitation for limitation in summary["limitations"])
    return "\n".join(rows) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        summary = rebuild(args.run_dir)
        args.out.mkdir(parents=True, exist_ok=False)
        write_json(args.out / "telemetry_summary.json", summary)
        (args.out / "telemetry_summary.md").write_text(markdown(summary), encoding="utf-8")
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "INCOMPLETE", "error": type(exc).__name__}))
        return 4
    print(
        json.dumps(
            {"status": summary["status"], "mode": summary["context"]["mode"], "out": str(args.out)}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
