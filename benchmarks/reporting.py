"""P10 deterministic reports from saved evidence. No providers or workloads run here."""

import json
from collections import defaultdict

from benchmarks.comparison import compare_runs
from benchmarks.dataset_checks import EXPECTED, SOURCE_SHA256
from benchmarks.performance import (
    CORE_CASES,
    checked_ref,
    load_performance_run,
    read_json,
    verified_bundle,
)
from benchmarks.planning import plan_matrix
from projectctl.artifacts import content_hash, file_hash, save_evidence, write_json
from projectctl.config import load_matrix, repo_path
from projectctl.models import EvaluationConfig, ExitCode, Summary
from projectctl.providers import DependencyError, ProviderResult
from projectctl.report_models import FinalReport, MatrixPlan, MatrixResults, ReportRun, ReportTable

TABLES = (
    ("dataset_quality_dispositions", True),
    ("import_I0_I1", True),
    ("stream_B0_O1", True),
    ("index_query_B0_O2", True),
    ("partition_scaling_skew", True),
    ("compaction_pruning", True),
    ("fault_replay_correctness_recovery", True),
    ("integrated_B0_C_BEST", True),
    ("stress_capacity_recovery", True),
    ("optional_assistant", False),
    ("optional_ANN", False),
)
LIMITATIONS = [
    "Three repetitions give descriptive median/min/max, not statistical significance.",
    "Completed-only quantiles retain unresolved counts; no unconditional p99 claim.",
    "Historical catalogue, simulated inventory/payments; only four verified apparel sizes.",
    "Missing facets remain null; source profiling is not a normalization/performance pass.",
    "Hardware, cache, clock, dataset scale and single-broker retained-volume limits apply.",
    "A memory/CPU increase is a cost; negative and zero-baseline results are retained.",
    "Optional assistant/ANN results are separate and cannot satisfy required core evidence.",
    "Release needs owner review and an independently reviewed clean setup rehearsal.",
]


def table_for(run):
    w, v, order = run.workload, run.variant, run.order
    if w == "W-AGENT":
        return "optional_assistant"
    if v in {"R-EXACT", "R-ANN"}:
        return "optional_ANN"
    if w == "W-IMPORT":
        return "import_I0_I1"
    if w == "W-SEARCH":
        return "index_query_B0_O2"
    if w == "W-ANALYTICS":
        return "compaction_pruning"
    if w == "W-INTEGRATED":
        return "integrated_B0_C_BEST"
    if w in {"W-CHECKOUT", "W-QUALITY"}:
        return "fault_replay_correctness_recovery"
    if order.get("stress_tier") or order.get("fault", "none") != "none":
        return "stress_capacity_recovery"
    if v in {"P10", "P30", "P33"}:
        return "partition_scaling_skew"
    return "stream_B0_O1"


def _index_file(index, path):
    path = path.resolve()
    relative = path.relative_to(repo_path(".")).as_posix()
    digest = file_hash(path)
    if relative in index and index[relative] != digest:
        raise DependencyError("evidence changed during report construction")
    index[relative] = digest


def _bundle(index, directory):
    manifest = verified_bundle(directory, {"summary.json"})
    _index_file(index, directory / "manifest.json")
    for ref in manifest["artifacts"]:
        _index_file(index, directory / ref["path"])
    return manifest


def _external_refs(index, value):
    """Include transitive repository-relative review/selection references in the export."""
    if isinstance(value, dict):
        if set(value) == {"path", "sha256"}:
            path = checked_ref(value)
            already = path.relative_to(repo_path(".")).as_posix() in index
            _index_file(index, path)
            if not already and path.suffix == ".json":
                data = read_json(path)
                if path.name == "manifest.json" and "run_id" in data and "command" in data:
                    _bundle(index, path.parent)
                else:
                    _external_refs(index, data)
        else:
            for child in value.values():
                _external_refs(index, child)
    elif isinstance(value, list):
        for child in value:
            _external_refs(index, child)


def _evaluation(path, index):
    """Rebuild each completed case's assertions from its immutable raw audit."""
    from benchmarks.integration import (
        bind_runtime_inputs,
        check_observation,
        load_case_review,
        validate_setup,
    )
    from benchmarks.integration_cases import expand_suites
    from benchmarks.integration_faults import validate_saved_fault

    directory = path.parent
    manifest = _bundle(index, directory)
    summary = Summary.model_validate(read_json(directory / "summary.json"))
    plan = read_json(directory / "case_plan.json")
    cases = expand_suites(plan["suite"])
    rows = [json.loads(line) for line in (directory / "tests.jsonl").read_text().splitlines()]
    if (
        summary.run_id != manifest["run_id"]
        or summary.namespace != manifest["namespace"]
        or summary.config_sha256 != manifest["config_sha256"]
    ):
        raise DependencyError("evaluation identity mismatch")
    if manifest["command"] != "eval run" or [r["case_id"] for r in rows] != [
        c.case_id for c in cases
    ]:
        raise DependencyError("evaluation journal differs from registered cases")
    rebuilt = []
    for case, row in zip(cases, rows, strict=True):
        item = {
            "case_id": case.case_id,
            "status": "NOT_RUN",
            "evidence": path.relative_to(repo_path(".")).as_posix(),
        }
        if row["status"] in {"PASS", "FAIL"}:
            if row["test_mode"] != "real" or summary.test_mode != "real":
                raise DependencyError("test-double evaluation cannot enter the real report")
            refs = row["artifact_refs"]
            if not refs:
                raise DependencyError("completed case has no raw evidence")
            for ref in refs:
                raw = (directory / ref["path"]).resolve()
                if not raw.is_relative_to(directory.resolve()) or file_hash(raw) != ref["sha256"]:
                    raise DependencyError("case evidence missing or changed")
                _index_file(index, raw)
            case_dir = directory / refs[0]["path"].split("/")[0]
            fixture = read_json(case_dir / "fixture.json")
            if fixture["content_sha256"] != content_hash(fixture) or (
                fixture["content_sha256"] != row["input_fixture_hash"]
            ):
                raise DependencyError("case fixture hash mismatch")
            bound = bind_runtime_inputs(fixture, read_json(case_dir / "exercise_receipt.json"))
            if bound != read_json(case_dir / "bound_fixture.json"):
                raise DependencyError("bound case expectations changed")
            review = load_case_review(case_dir, row["namespace"])
            _external_refs(index, review["contracts"])
            context = {"namespace": row["namespace"], "run_id": manifest["run_id"]}
            validate_setup(read_json(case_dir / "setup.json"), context, real=True)
            validate_saved_fault(case, context, directory, row)
            assertions, _ = check_observation(
                case,
                bound,
                read_json(case_dir / "observed.json"),
                context,
                review,
            )
            item["status"] = (
                "PASS" if assertions and all(a["passed"] for a in assertions) else "FAIL"
            )
        elif row["status"] != "NOT_RUN":
            item["status"] = "INCOMPLETE"
        rebuilt.append(item)
    return manifest, rebuilt


def _comparisons(runs, blockers):
    groups = defaultdict(lambda: defaultdict(list))
    for run in runs:
        if run.workload is None:
            continue
        key = (run.workload, run.order.get("matrix_row"), content_hash(run.order.get("series", {})))
        treatment = (run.variant, run.order.get("layout_child"), run.order.get("fault", "none"))
        groups[key][treatment].append(run)
    reports = []
    for key, treatments in sorted(groups.items(), key=lambda item: str(item[0])):
        workload = key[0]
        pairs = []
        for candidate in treatments:
            variant, child, fault = candidate
            base = None
            if variant in {"O1", "O2", "O3", "F-COMPACT", "R-ANN"}:
                base = ("B0" if variant != "R-ANN" else "R-EXACT", None, fault)
            elif variant == "I1":
                base = ("I0", None, fault)
            elif variant in {"P30", "P33"}:
                base = ("P10" if variant == "P30" else "P30", None, fault)
            elif variant == "F-PARTITION" and child == "date_type":
                base = (variant, "unpartitioned", fault)
            elif workload == "W-CHECKOUT" and fault != "none":
                base = ("B0", None, "none")
            if base is not None:
                pairs.append((base, candidate))
        for base, candidate in pairs:
            left, right = treatments.get(base, []), treatments[candidate]
            label = f"{workload}/{key[1]}/{base}/{candidate}"
            try:
                # This revalidates hashes, controls, all 1/2/3 repetitions and raw metrics.
                report = compare_runs(
                    [r.evidence_dir for r in left], [r.evidence_dir for r in right]
                )
                reports.append(report)
                if report["status"] != "MEASURED":
                    blockers.append("incomplete comparison: " + label)
            except (DependencyError, OSError, ValueError, KeyError, TypeError):
                blockers.append("unavailable/incomparable paired repetitions: " + label)
    return reports


def build_report(matrix_results):
    """Pure saved-input reconstruction; returns a validated report including blockers."""
    source = repo_path(matrix_results)
    index, blockers, runs, correctness, configs = {}, [], [], [], []
    _index_file(index, source)
    data = MatrixResults.model_validate(read_json(source)).model_dump(exclude_none=True)
    plan_path = (source.parent / data["plan"]).resolve()
    if not plan_path.is_relative_to(source.parent.resolve()):
        raise DependencyError("matrix plan must stay beside result bundle")
    _index_file(index, plan_path)
    plan = MatrixPlan.model_validate(read_json(plan_path)).model_dump()
    if plan["schema_version"] != 1 or plan["pending"] != data["pending"]:
        raise DependencyError("matrix plan/pending mismatch")
    planned = {o["trial_key"]: o for o in plan["trials"]}
    if len(planned) != len(plan["trials"]):
        raise DependencyError("duplicate planned trials")
    seen_ids, seen_trials, namespaces = set(), set(), set()
    for record in data["runs"]:
        directory = repo_path(record["evidence_dir"])
        manifest = _bundle(index, directory)
        summary = Summary.model_validate(read_json(directory / "summary.json"))
        if (
            summary.run_id != record["run_id"]
            or summary.run_id != manifest["run_id"]
            or summary.namespace != manifest["namespace"]
            or summary.config_sha256 != manifest["config_sha256"]
            or record["exit_code"] != summary.exit_code
            or summary.run_id in seen_ids
            or summary.namespace in namespaces
        ):
            raise DependencyError("matrix run identity/namespace/status mismatch or duplicate")
        seen_ids.add(summary.run_id)
        namespaces.add(summary.namespace)
        order_path = directory / "execution_order.json"
        order = read_json(order_path) if order_path.exists() else {}
        if order:
            if order["trial_key"] not in planned or order != planned[order["trial_key"]]:
                # Reused trials can have an older session/order index, never different controls.
                stable = set(order) - {"session_id", "pair_id", "execution_index"}
                expected = planned.get(order["trial_key"], {})
                if {k: order[k] for k in stable} != {
                    k: v for k, v in expected.items() if k in stable
                } or set(order) != set(expected):
                    raise DependencyError("run treatment differs from planned trial")
            if order["trial_key"] in seen_trials:
                raise DependencyError("duplicate trial evidence; retain exactly one run per trial")
            seen_trials.add(order["trial_key"])
        metrics = []
        status = "NOT_RUN" if manifest["started_at"] is None else "INCOMPLETE"
        reasons = list(summary.reasons)
        if summary.test_mode == "stub" or (
            summary.test_mode != "real" and any(m.status == "MEASURED" for m in summary.metrics)
        ):
            raise DependencyError("test-double measurements cannot enter a real report")
        if summary.exit_code == 0 and summary.status == "MEASURED":
            try:
                verified = load_performance_run(directory)
                metrics = verified["summary"]["metrics"]
                status = "MEASURED"
            except (DependencyError, OSError, ValueError, KeyError, TypeError):
                reasons.append("raw performance evidence invalid; values withheld")
        optional = manifest["workload_id"] == "W-AGENT" or manifest["variant_id"] in {
            "R-EXACT",
            "R-ANN",
            "A-ASSIST",
        }
        if status != "MEASURED" and not optional:
            blockers.append(f"{summary.run_id}: {status}; exit={summary.exit_code}")
        context = {"git": manifest["git"], "host": manifest["host"], "locks": manifest["locks"]}
        if status == "MEASURED":
            from benchmarks.observation_summary import rebuild

            telemetry = rebuild(directory)
            context["telemetry"] = {k: telemetry[k] for k in ("series", "rates", "latencies")}
            for name in ("performance_review.json", "binding_review.json"):
                _external_refs(index, read_json(directory / name))
            if (directory / "import_timings.json").is_file():
                context["import_timings"] = read_json(directory / "import_timings.json")
        if manifest["resolved_config"]:
            config = EvaluationConfig.model_validate(manifest["resolved_config"])
            if content_hash(config.model_dump()) != manifest["config_sha256"]:
                raise DependencyError("resolved configuration hash mismatch")
            configs.append(config)
            context["dataset"] = config.dataset.model_dump()
            context["profile"] = config.profile.model_dump()
            context["retrieval"] = config.retrieval.model_dump()
        runs.append(
            ReportRun(
                run_id=summary.run_id,
                evidence_dir=record["evidence_dir"],
                workload=manifest["workload_id"],
                variant=manifest["variant_id"],
                repetition=manifest["repetition"],
                namespace=summary.namespace,
                config_sha256=summary.config_sha256,
                manifest_sha256=file_hash(directory / "manifest.json"),
                status=status,
                test_mode=summary.test_mode,
                exit_code=summary.exit_code,
                correctness_passed=manifest["correctness_passed"],
                metrics=metrics,
                reasons=reasons,
                order=order,
                context=context,
            )
        )
    if seen_trials != set(planned):
        blockers.append("matrix is missing planned trial evidence")
    support = data.get("support", {})
    if set(support) - {"dataset_checks", "evaluations", "selection", "conclusions", "rehearsal"}:
        raise DependencyError("unknown report support field")
    dataset = None
    for refs in support.values():
        for ref in refs if isinstance(refs, list) else [refs]:
            _index_file(index, checked_ref(ref))
    if "dataset_checks" in support:
        dataset = read_json(checked_ref(support["dataset_checks"]))
        if (
            dataset.get("status") != "PASS"
            or dataset.get("source_sha256") != SOURCE_SHA256
            or dataset.get("observed") != EXPECTED
            or not dataset.get("assertions")
            or not all(a.get("passed") is True for a in dataset["assertions"])
        ):
            blockers.append("dataset source checks failed or incomplete")
    else:
        blockers.append("dataset source checks NOT_RUN")
    for ref in support.get("evaluations", []):
        evaluation, rows = _evaluation(checked_ref(ref), index)
        correctness.extend(rows)
        measured = [r for r in runs if r.status == "MEASURED"]
        if measured and evaluation["git"] != measured[0].context["git"]:
            blockers.append("correctness and measurement revisions differ")
        if any(r["status"] != "PASS" for r in rows):
            blockers.append("real correctness cases failed or incomplete")
    passed = {r["case_id"] for r in correctness if r["status"] == "PASS"}
    blockers.extend("correctness NOT_RUN/INCOMPLETE: " + c for c in sorted(CORE_CASES - passed))
    selection = None
    if configs:
        if "selection" in support:
            from benchmarks.selection import load_selection

            selection = load_selection(support["selection"]["path"], configs[0])
            _external_refs(index, read_json(checked_ref(support["selection"])))
        required, pending = plan_matrix(
            configs[0], load_matrix("configs/core_matrix.yaml", configs[0]), selection
        )
        if {t.order["trial_key"] for t in required} != set(planned) or pending:
            blockers.append("full required matrix/selected stress/recovery evidence incomplete")
    else:
        blockers.append("no resolved matrix configuration")
    blockers.extend("pending matrix row: " + str(row) for row in data["pending"])
    optional_issues = []
    comparisons = _comparisons(
        [r for r in runs if table_for(r) not in {"optional_assistant", "optional_ANN"}], blockers
    ) + _comparisons(
        [r for r in runs if table_for(r) in {"optional_assistant", "optional_ANN"}], optional_issues
    )
    measured = [r for r in runs if r.status == "MEASURED"]
    if measured and any(
        (r.context["git"], r.context["locks"], r.context.get("dataset"))
        != (
            measured[0].context["git"],
            measured[0].context["locks"],
            measured[0].context.get("dataset"),
        )
        for r in measured
    ):
        blockers.append("matrix changes frozen code/locks/source/dictionary inputs")
    if not support.get("conclusions"):
        blockers.append("owner bottleneck/conclusion/cost review NOT_RUN")
    if not support.get("rehearsal"):
        blockers.append("clean setup rehearsal NOT_RUN")
    else:
        rehearsal = read_json(checked_ref(support["rehearsal"]))
        if (
            rehearsal.get("real_setup_status") != "PASS"
            or rehearsal.get("locked_install_passed") is not True
            or rehearsal.get("report_rebuild_identical") is not True
            or rehearsal.get("missing_evidence_detected") is not True
            or rehearsal.get("source_sha256") != SOURCE_SHA256
        ):
            blockers.append("clean setup rehearsal INCOMPLETE")
    tables = []
    for name, required in TABLES:
        members = [r for r in runs if table_for(r) == name]
        status = (
            "MEASURED"
            if members and all(r.status == "MEASURED" for r in members)
            else "INCOMPLETE"
            if any(r.status != "NOT_RUN" for r in members)
            else "NOT_RUN"
        )
        if name == "dataset_quality_dispositions":
            status = "NOT_RUN"
            if dataset and dataset.get("status") == "PASS":
                status = (
                    "MEASURED"
                    if dataset.get("provider_normalization_comparison") == "PASS"
                    and dataset.get("facet_coverage_verification") == "PASS"
                    else "INCOMPLETE"
                )
        if required and status != "MEASURED":
            blockers.append(name + ": " + status)
        tables.append(
            ReportTable(
                name=name, required=required, status=status, run_ids=[r.run_id for r in members]
            )
        )
    targets = []
    for run in runs:
        for metric in run.metrics:
            if metric.name == "producer_to_gold_p95_ms":
                targets.append(
                    {
                        "run_id": run.run_id,
                        "metric": metric.name,
                        "unit": metric.unit,
                        "target": 1000,
                        "value": metric.value,
                        "met": metric.value <= 1000 if metric.value is not None else None,
                    }
                )
    report = FinalReport(
        schema_version=1,
        status="INCOMPLETE" if blockers else "MEASURED",
        required_core_complete=not blockers,
        release_status="INCOMPLETE" if blockers else "REVIEW_REQUIRED",
        runs=sorted(runs, key=lambda r: r.run_id),
        tables=tables,
        comparisons=comparisons,
        dataset_checks=dataset,
        correctness=correctness,
        targets=targets,
        limitations=LIMITATIONS + optional_issues,
        not_run=sorted(set(blockers)),
        evidence_index=[{"path": p, "sha256": h} for p, h in sorted(index.items())],
    ).model_dump()
    report["content_sha256"] = content_hash(report)
    return report


def markdown(report):
    def cell(value):
        return str(value if value is not None else "null").replace("|", "\\|").replace("\n", " ")

    lines = [
        "# Evidence report",
        "",
        f"Status: **{report['status']}**; release: **{report['release_status']}**.",
        "",
        "All repetitions and failures are retained.",
        "",
    ]
    by_id = {r["run_id"]: r for r in report["runs"]}
    for table in report["tables"]:
        lines += [
            "## " + table["name"],
            "",
            "Status: " + table["status"],
            "",
            "| Workload | Variant | Rep | Status | Correctness | Evidence |",
            "|---|---|---|---|---|---|",
        ]
        for run_id in table["run_ids"]:
            r = by_id[run_id]
            lines.append(
                "| "
                + " | ".join(
                    map(
                        cell,
                        [
                            r["workload"],
                            r["variant"],
                            r["repetition"],
                            r["status"],
                            r["correctness_passed"],
                            r["evidence_dir"],
                        ],
                    )
                )
                + " |"
            )
        if table["name"] == "dataset_quality_dispositions" and report["dataset_checks"]:
            lines += ["", "```json", json.dumps(report["dataset_checks"], sort_keys=True), "```"]
    lines += [
        "",
        "## Metrics and raw trace",
        "",
        "| Run | Metric | Unit | Value | Samples | Numerator | Denominator | Unresolved | "
        "Cohort | Quantile | Timing | Config SHA | Status | Raw evidence |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in report["runs"]:
        for m in r["metrics"]:
            values = [
                r["run_id"],
                m["name"],
                m["unit"],
                m["value"],
                m["sample_count"],
                m["numerator"],
                m["denominator"],
                m["unresolved_count"],
                m["cohort"],
                m["quantile_method"],
                m["timing_validity"],
                m["config_sha256"],
                m["status"],
                r["evidence_dir"] + "/" + m["evidence_path"],
            ]
            lines.append("| " + " | ".join(map(cell, values)) + " |")
    lines += [
        "",
        "## Paired comparisons",
        "",
        "| Workload | Candidate | Metric | Unit/cohort/method/timing | Baseline median/min/max | "
        "Candidate median/min/max | Improvement % | Absolute change | Samples | Unresolved |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for comparison in report["comparisons"]:
        for m in comparison["metrics"]:
            values = [
                comparison["workload"],
                comparison["candidate_variant"],
                m["name"],
                m["semantics"],
                m["baseline"],
                m["candidate"],
                m["improvement_percent"],
                m.get("absolute_change"),
                m["sample_counts"],
                m["unresolved_counts"],
            ]
            lines.append("| " + " | ".join(map(cell, values)) + " |")
    lines += [
        "",
        "## Targets",
        "",
        "```json",
        json.dumps(report["targets"], sort_keys=True),
        "```",
        "",
        "## Limitations and costs",
        "",
    ]
    lines += ["- " + item for item in report["limitations"]]
    lines += ["", "## Remaining evidence", ""] + ["- " + item for item in report["not_run"]]
    return "\n".join(lines) + "\n"


def execute_report(invocation):
    directory = repo_path(invocation.arguments["out"])
    try:
        report = build_report(invocation.arguments["matrix_results"])
        code = (
            ExitCode.COMPLETED if report["required_core_complete"] else ExitCode.DEPENDENCY_FAILURE
        )
    except (DependencyError, OSError, ValueError, KeyError, TypeError):
        # No invalid values survive into the report; retain a reviewable refusal artifact.
        report = FinalReport(
            schema_version=1,
            status="INCOMPLETE",
            required_core_complete=False,
            release_status="INCOMPLETE",
            runs=[],
            tables=[],
            comparisons=[],
            dataset_checks=None,
            correctness=[],
            targets=[],
            limitations=LIMITATIONS,
            not_run=["input/evidence invalid or unavailable; no measurements accepted"],
            evidence_index=[],
        ).model_dump()
        report["content_sha256"] = content_hash(report)
        code = ExitCode.DEPENDENCY_FAILURE
    directory.mkdir(parents=True, exist_ok=False)
    write_json(directory / "report.json", report)
    write_json(directory / "evidence-index.json", {"artifacts": report["evidence_index"]})
    (directory / "report.md").write_text(markdown(report), encoding="utf-8", newline="\n")
    return save_evidence(
        invocation,
        ProviderResult(code, (invocation.arguments["out"] + "/report.json",), "offline"),
        execution=None,
    )
