"""P9 evidence eligibility. A provider registration alone never authorizes a baseline."""

import json
from pathlib import Path

from benchmarks.integration_cases import expand_suites
from projectctl.artifacts import content_hash, file_hash, git_state
from projectctl.config import repo_path
from projectctl.models import EvaluationConfig, RunManifest, Summary
from projectctl.providers import DependencyError

REVIEWERS = {"Jaineel", "Harsh", "Aditya", "Vichitr"}
CORE_CASES = {c.case_id for c in expand_suites(["correctness", "smoke", "T-10", "T-11"])}
BASE_FILES = {
    "resolved_config.json",
    "summary.json",
    "execution.json",
    "execution_order.json",
    "planned.jsonl",
    "emissions.jsonl",
    "generator.json",
    "admission.json",
    "audit.json",
    "correctness.json",
    "workload_manifest.json",
    "timings.parquet",
    "resources.csv",
    "telemetry_manifest.json",
    "observation_context.json",
    "observations.jsonl",
    "observation_end.json",
    "expected.json",
    "observed.json",
    "binding_review.json",
    "performance_validation.json",
    "performance_review.json",
    "resource_receipt.json",
}
STREAM_WORKLOADS = {"W-PIPE", "W-QUALITY", "W-CHECKOUT", "W-INTEGRATED"}


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    return json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")),
    )


def checked_ref(ref):
    if set(ref) != {"path", "sha256"}:
        raise DependencyError("exact path/SHA-256 evidence reference required")
    path = repo_path(ref["path"])
    if not path.is_file() or file_hash(path) != ref["sha256"]:
        raise DependencyError("reviewed evidence file missing or changed")
    return path


def controls_hash(config):
    """Study identity shared by declared rate/mode/skew/treatment series."""
    data = config.model_dump()
    generator = data["generator"]
    for key in ("rate_per_second", "key_distribution"):
        generator.pop(key)
    retrieval = data["retrieval"]
    retrieval.pop("mode")
    return content_hash(
        {
            key: data[key]
            for key in ("profile", "dataset", "locks", "assistant", "generator", "retrieval")
        }
        | {"templates": {k: v["template_sha256"] for k, v in data["workloads"].items()}}
    )


def reviewed_recipe(review_path, recipe):
    """Rate/skew/smoke schedules need their own frozen recipe, not a substituted hash."""
    review = read_json(repo_path(review_path))
    for ref in review["inputs"]:
        path = checked_ref(ref)
        if path.suffix == ".json":
            value = read_json(path)
            if value == recipe:
                return True
    return False


def verified_bundle(directory, required=()):
    """Verify every indexed file before consuming it; reject traversal and partial indexes."""
    directory = Path(directory).resolve()
    manifest = read_json(directory / "manifest.json")
    RunManifest.model_validate(manifest)
    if manifest["content_sha256"] != content_hash(manifest):
        raise DependencyError("run manifest hash mismatch")
    indexed = set()
    for ref in manifest["artifacts"]:
        path = (directory / ref["path"]).resolve()
        if (
            path in indexed
            or not path.is_relative_to(directory)
            or not path.is_file()
            or file_hash(path) != ref["sha256"]
        ):
            raise DependencyError("run artifact missing, duplicated, outside run, or changed")
        indexed.add(path)
    if any((directory / name).resolve() not in indexed for name in required):
        raise DependencyError("required evidence not indexed by run manifest")
    return manifest


def review_blockers(config, review_path, *, qualified=False, require_smoke=False):
    """Review receipt is an explicit owner handoff, never generated from test doubles."""
    reasons = []
    state = git_state()
    if state.dirty is not False or state.commit is None:
        reasons.append("final measurements require a clean committed code revision")
    if review_path is None:
        return reasons + ["P9 reviewed real correctness/resource receipt unavailable"]
    try:
        review = read_json(repo_path(str(review_path)))
        allowed = {
            "schema_version",
            "content_sha256",
            "reviewers",
            "git_commit",
            "controls_sha256",
            "resource_receipt",
            "correctness_runs",
            "inputs",
            "smoke_run",
            "baseline_run",
            "diagnosis",
            "hypotheses",
        }
        if (
            set(review) != allowed
            or review["schema_version"] != 1
            or review["content_sha256"] != content_hash(review)
            or set(review["reviewers"]) != REVIEWERS
            or review["git_commit"] != state.commit
            or review["controls_sha256"] != controls_hash(config)
        ):
            raise DependencyError("P9 review identity/controls/owner review mismatch")
        resource = read_json(checked_ref(review["resource_receipt"]))
        if (
            resource.get("test_mode") != "real"
            or resource.get("enforced") is not True
            or resource.get("profile") != config.profile.model_dump()
            or resource.get("git_commit") != state.commit
            or not resource.get("image_digests")
            or not all(
                isinstance(d, str) and "@sha256:" in d and len(d.rsplit("@sha256:", 1)[1]) == 64
                for d in resource["image_digests"]
            )
            or not all(
                resource.get("host", {}).get(k)
                for k in ("cpu_model", "physical_cores", "total_memory_bytes", "os", "storage")
            )
        ):
            raise DependencyError("actual enforced allocations, host and pinned images required")
        inputs = {str(checked_ref(ref)): ref["sha256"] for ref in review["inputs"]}
        required_inputs = {
            config.dataset.source_path,
            config.dataset.dictionary_path,
            config.dataset.canonical_manifest,
            config.dataset.sku_manifest,
        }
        if None in required_inputs or any(str(repo_path(p)) not in inputs for p in required_inputs):
            raise DependencyError("exact source/dictionary/canonical/SKU input hashes required")
        logical_hashes = set(inputs.values())
        for path in inputs:
            if Path(path).suffix == ".json":
                value = read_json(path)
                logical_hashes.add(content_hash(value))
                if value.get("logical_fixture_sha256"):
                    logical_hashes.add(value["logical_fixture_sha256"])
        if config.generator.template_sha256 not in logical_hashes or any(
            item.template_sha256 not in logical_hashes
            for name, item in config.workloads.items()
            if name != "W-AGENT"
        ):
            raise DependencyError("frozen logical fixture files/hashes required")
        cases = set()
        for ref in review["correctness_runs"]:
            path = checked_ref(ref)
            manifest = verified_bundle(
                path.parent, {"summary.json", "tests.jsonl", "correctness.json"}
            )
            summary = Summary.model_validate(read_json(path.parent / "summary.json"))
            if (
                path.name != "manifest.json"
                or manifest["command"] != "eval run"
                or manifest["git"] != state.model_dump()
                or summary.test_mode != "real"
                or summary.exit_code != 0
                or manifest["correctness_passed"] is not True
                or controls_hash(EvaluationConfig.model_validate(manifest["resolved_config"]))
                != controls_hash(config)
            ):
                raise DependencyError("same-revision real correctness evidence required")
            correctness = read_json(path.parent / "correctness.json")
            rows = [
                json.loads(line)
                for line in (path.parent / "tests.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            if (
                correctness.get("real_integration_passed") is not True
                or correctness.get("cases") != rows
                or not rows
            ):
                raise DependencyError("real correctness journal/result mismatch")
            for row in rows:
                if (
                    row.get("status") != "PASS"
                    or row.get("test_mode") != "real"
                    or not row.get("assertions")
                    or any(a.get("passed") is not True for a in row["assertions"])
                ):
                    raise DependencyError("skipped, missing or failed real correctness cases")
                if not row.get("artifact_refs"):
                    raise DependencyError("correctness raw evidence references missing")
                for ref in row["artifact_refs"]:
                    raw = (path.parent / ref["path"]).resolve()
                    if (
                        not raw.is_relative_to(path.parent.resolve())
                        or file_hash(raw) != ref["sha256"]
                    ):
                        raise DependencyError("correctness raw case evidence changed")
                cases.add(row["case_id"])
        if not CORE_CASES <= cases:
            raise DependencyError("mandatory real correctness/smoke/T-10/T-11 coverage incomplete")
        if qualified or require_smoke:
            for kind in ("smoke", "baseline") if qualified else ("smoke",):
                path = checked_ref(review[kind + "_run"])
                run = load_performance_run(
                    path.parent, kind="smoke" if kind == "smoke" else "performance"
                )
                if (
                    run["manifest"]["git"] != state.model_dump()
                    or run["manifest"]["variant_id"] != "B0"
                ):
                    raise DependencyError("qualification must use the frozen B0 revision")
                if controls_hash(run["config"]) != controls_hash(config):
                    raise DependencyError("qualification changes study controls")
        if qualified:
            if not checked_ref(review["diagnosis"]).read_text(encoding="utf-8").strip():
                raise DependencyError("actual B0 bottleneck diagnosis required before candidates")
            if not review["hypotheses"]:
                raise DependencyError("predeclared optimization hypotheses required")
            for ref in review["hypotheses"]:
                if not checked_ref(ref).read_text(encoding="utf-8").strip():
                    raise DependencyError("empty optimization hypothesis")
    except (DependencyError, OSError, ValueError, KeyError, TypeError) as exc:
        reasons.append(
            str(exc)
            if isinstance(exc, DependencyError)
            else "P9 reviewed evidence unavailable or invalid; no fallback used"
        )
    return reasons


def load_performance_run(directory, *, kind="performance"):
    directory = Path(directory).resolve()
    manifest = verified_bundle(directory, BASE_FILES)
    summary = Summary.model_validate(read_json(directory / "summary.json"))
    config = EvaluationConfig.model_validate(manifest["resolved_config"])
    order = read_json(directory / "execution_order.json")
    execution = read_json(directory / "execution.json")
    validation = read_json(directory / "performance_validation.json")
    if (
        manifest["status"] != "MEASURED"
        or manifest["correctness_passed"] is not True
        or manifest["git"]["dirty"] is not False
        or not manifest["git"]["commit"]
        or summary.status != "MEASURED"
        or summary.exit_code != 0
        or summary.test_mode != "real"
        or summary.run_id != manifest["run_id"]
        or summary.namespace != manifest["namespace"]
        or summary.config_sha256 != manifest["config_sha256"]
        or manifest["config_sha256"] != content_hash(config.model_dump())
        or read_json(directory / "resolved_config.json") != config.model_dump()
        or execution.get("test_mode") != "real"
        or execution.get("evidence_kind") != kind
        or execution.get("sut_performance") != ("MEASURED" if kind == "performance" else "NOT_RUN")
        or execution.get("fixture_only")
        or validation.get("passed") is not True
        or not manifest["host"]["resources_verified"]
        or config.profile.allocation_status != "enforced"
    ):
        raise DependencyError("complete real clean-revision performance evidence required")
    protocol = manifest["workload_protocol"]
    if (
        kind == "performance"
        and protocol["kind"] == "sustained"
        and (protocol["warmup_seconds"], protocol["duration_seconds"], protocol["drain_seconds"])
        != (60, 600, 120)
    ):
        raise DependencyError("short smoke/invalid drain cannot be a sustained measurement")
    if (
        kind == "performance"
        and protocol["kind"] == "queries"
        and (
            protocol["query_count"],
            protocol["warmups_per_query"],
            protocol["executions_per_query"],
        )
        != (6, 3, 30)
    ):
        raise DependencyError("analytical query protocol differs from Q1-Q6 3/30")
    validation = validate_outputs(
        directory,
        {
            "workload_id": manifest["workload_id"],
            "namespace": manifest["namespace"],
            "run_id": manifest["run_id"],
            "fault_profile": order.get("fault", "none"),
        },
    )
    if validation["passed"] is not True:
        raise DependencyError("raw audit/collector evidence failed independent recheck")
    return {
        "directory": directory,
        "manifest": manifest,
        "summary": summary.model_dump(),
        "config": config,
        "order": order,
    }


def validate_outputs(directory, context):
    """Independently recheck provider audit and required collector products before promotion."""
    from benchmarks.integration import validate_review
    from benchmarks.observation_summary import rebuild
    from benchmarks.reconciliation import reconcile_run

    failures = []
    correctness_failed = False
    workload = context["workload_id"]
    required = BASE_FILES - {
        "performance_validation.json",
        "resolved_config.json",
        "summary.json",
        "execution.json",
    }
    if workload in STREAM_WORKLOADS:
        required |= {"lag.csv", "gold_visibility.jsonl"}
    if workload == "W-IMPORT":
        required |= {"import_timings.json"}
    if workload in {"W-SEARCH", "W-ANALYTICS"}:
        required |= {"query_results.parquet"}
    if workload in {"W-SEARCH", "W-ANALYTICS", "W-INTEGRATED"}:
        required |= {"plans", "manifests"}
    for name in sorted(required):
        path = directory / name
        if (
            not path.exists()
            or (path.is_file() and not path.stat().st_size)
            or (path.is_dir() and not any(p.is_file() for p in path.rglob("*")))
        ):
            failures.append("missing raw evidence: " + name)
    try:
        expected, observed = (
            read_json(directory / "expected.json"),
            read_json(directory / "observed.json"),
        )
        if (
            expected.get("namespace") != context["namespace"]
            or observed.get("namespace") != context["namespace"]
            or observed.get("test_mode") != "real"
        ):
            raise DependencyError("real namespace-scoped audit required")
        review = validate_review(
            directory / "binding_review.json", context["namespace"], directory / "expected.json"
        )
        if workload in STREAM_WORKLOADS:
            verdict = reconcile_run(expected, observed, binding_review=review)
            if verdict["reconciliation"]["passed"] is not True:
                failures.append("independent business/data reconciliation failed")
                correctness_failed = verdict["status"] == "FAIL"
        else:
            from benchmarks.reconciliation import compare_fixture_output

            logical = expected.get("logical_results")
            if (
                not logical
                or observed.get("collection_complete") is not True
                or not compare_fixture_output(logical, observed.get("logical_results"))["passed"]
            ):
                failures.append("independent import/query logical results differ or missing")
                correctness_failed = bool(logical) and observed.get("collection_complete") is True
        telemetry = rebuild(directory)
        if telemetry["status"] != "MEASURED" or telemetry["context"]["mode"] != "real":
            failures.append("collector samples incomplete or not real")
        names = {row["metric"] for row in telemetry["series"]}
        needed = {"process_cpu_seconds_total", "process_resident_memory_bytes"}
        if workload in STREAM_WORKLOADS:
            needed |= {"kafka_consumer_lag", "gold_pending_events", "outbox_pending"}
        if not needed <= names or any(
            c["mode"] != "real" for c in telemetry["context"]["collectors"]
        ):
            failures.append("required real resource/lag/backlog collectors missing")
        if (
            telemetry["context"]["namespace"] != context["namespace"]
            or telemetry["context"]["workload"] != workload
            or not telemetry["context"]["shared_host_clock"]
        ):
            failures.append("collector namespace/workload/shared clock differs")
        if context.get("fault_profile", "none") != "none":
            receipts = [
                json.loads(line)
                for line in (directory / "faults.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            if (
                len(receipts) != 1
                or receipts[0].get("acknowledged") is not True
                or not receipts[0].get("injected_at")
                or not receipts[0].get("recovered_at")
                or receipts[0].get("namespace") != context["namespace"]
            ):
                failures.append("named fault acknowledgement/recovery evidence incomplete")
    except (DependencyError, OSError, ValueError, KeyError, TypeError):
        failures.append("independent audit/telemetry evidence unavailable or invalid")
    return {
        "schema_version": 1,
        "passed": not failures,
        "reasons": failures,
        "correctness_failed": correctness_failed,
    }
