"""P8 execution and independent evidence validation, never implicit provider stubs."""

import asyncio
import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from benchmarks.integration_cases import expand_suites
from benchmarks.integration_faults import FaultGate
from benchmarks.reconciliation import reconcile_run
from benchmarks.scheduler import journal, utc_now
from projectctl.artifacts import content_hash, file_hash, save_evidence, write_json
from projectctl.config import repo_path
from projectctl.models import ExitCode, RunManifest
from projectctl.providers import DependencyError, ProviderResult

REVIEWERS = {"Jaineel", "Harsh", "Aditya", "Vichitr"}


async def owner_call(awaitable, *, timeout):
    """External callback failures must not copy DSNs/tokens into public evidence."""
    try:
        return await asyncio.wait_for(awaitable, timeout)
    except Exception as exc:
        raise DependencyError(
            f"owner callback failed: {type(exc).__name__}; no fallback used"
        ) from None


@dataclass(frozen=True)
class CaseBinding:
    """Explicit consumer adapter, with frozen independent fixture before execution.

    prepare(ctx) returns namespace/created_new and setup proof. exercise(ctx,
    fixture, fault_gate) drives public APIs/SDKs and writes raw receipts into the
    case directory. audit(ctx) collects namespace-scoped read-only projections;
    it is not passed the expected answer. No callback may issue corrective writes.
    Real projection mappings/fixtures require all affected owners' review.
    """

    mode: str
    fixture_path: Path
    prepare: object
    exercise: object
    audit: object
    review_path: Path | None = None
    fault_hooks: object = None


def validate_review(path, namespace, fixture_path):
    """Verify frozen reviewed export/fixture mappings against actual local bytes."""
    review = json.loads(path.read_text(encoding="utf-8"))
    if (
        review.get("schema_version") != 1
        or review.get("read_only_audit") is not True
        or review.get("namespace_scoped") is not True
        or set(review.get("reviewers", [])) != REVIEWERS
        or not review.get("contracts")
        or review.get("fixture_sha256") != file_hash(fixture_path)
    ):
        raise DependencyError("read-only scoped audit/export review required from all owners")
    for ref in review["contracts"]:
        target = repo_path(ref["path"])
        if not re.fullmatch(r"[0-9a-f]{64}", ref["sha256"]) or file_hash(target) != ref["sha256"]:
            raise DependencyError("reviewed contract/export binding hash changed")
    return {
        "namespace": namespace,
        "review_sha256": file_hash(path),
        "reviewers": sorted(REVIEWERS),
        "contracts": review["contracts"],
    }


def validate_setup(setup, context, *, real):
    if setup.get("namespace") != context["namespace"] or setup.get("created_new") is not True:
        raise DependencyError("fresh isolated case namespace was not acknowledged")
    if not real:
        return
    required = {
        "postgresql_real",
        "kafka_real",
        "locked_environment",
        "source_verified",
        "import_verified",
        "sku_manifest_verified",
        "simulator_seed_verified",
        "complete_stock_projection",
        "benchmark_mode",
        "fault_injection_enabled",
    }
    if any(setup.get(key) is not True for key in required):
        raise DependencyError(
            "real PostgreSQL/Kafka, locks, manifests, seed/projection proof missing"
        )
    if setup.get("active_sku_count") != 19920 or setup.get("projected_sku_count") != 19920:
        raise DependencyError("all 19,920 active SKUs must cross the initial projection barrier")


def bind_runtime_inputs(fixture, receipt):
    """Bind runtime IDs/source facts, never learn expected business results from Gold.

    Generated UUIDs are not predictable fixture labels. Reviewed exercise adapters
    capture them and immutable producer/broker inputs before the separate sink audit.
    Only explicit null source slots and @id: tokens may be filled at this boundary.
    All expected prices, quantities, outcomes and Gold values stay frozen.
    """
    receipt = receipt or {}
    if set(receipt) - {"identities", "source_expectations"}:
        raise DependencyError("exercise receipt cannot replace independent business expectations")
    identities = receipt.get("identities", {})
    for key, value in identities.items():
        if not re.fullmatch(r"@id:[a-z][a-z0-9_-]*", key) or str(UUID(value)) != value:
            raise DependencyError("runtime identity binding must map a declared token to a UUID")
    bound = copy.deepcopy(fixture)
    source = receipt.get("source_expectations", {})
    if set(source) - {"events", "source_dispositions", "source_manifest_ids"}:
        raise DependencyError("runtime source receipt cannot supply expected business aggregates")
    for key, value in source.items():
        if bound["expected"].get(key, "absent") is not None:
            raise DependencyError("runtime source receipt cannot rewrite frozen input expectations")
        bound["expected"][key] = value

    def replace(value):
        if isinstance(value, str) and value.startswith("@id:"):
            if value not in identities:
                raise DependencyError("runtime identity token was not captured")
            return identities[value]
        if isinstance(value, dict):
            return {replace(key): replace(child) for key, child in value.items()}
        if isinstance(value, list):
            return [replace(child) for child in value]
        return value

    result = replace(bound)
    result.pop("content_sha256", None)
    result["source_fixture_sha256"] = fixture.get("content_sha256")
    result["content_sha256"] = content_hash(result)
    return result


def check_observation(case, fixture, observed, context, review=None):
    """Assertions are frozen by the harness, never accepted as provider pass flags."""
    assertions = []

    def check(name, expected, actual):
        assertions.append(
            {
                "name": name,
                "expected": expected,
                "observed": actual,
                "passed": type(expected) is type(actual) and expected == actual,
            }
        )

    check("namespace", context["namespace"], observed.get("namespace"))
    check("run_id", context["run_id"], observed.get("run_id"))
    check("case_id", case.case_id, observed.get("case_id"))
    check("collection_complete", True, observed.get("collection_complete"))
    for name, expected in case.checks:
        check(name, expected, observed.get("facts", {}).get(name))
    reconciliation = None
    if case.reconcile:
        expected = copy.deepcopy(fixture["expected"])
        expected["namespace"] = context["namespace"]
        reconciliation = reconcile_run(expected, observed["audit"], binding_review=review)
        check("independent_reconciliation", "PASS", reconciliation["status"])
        if case.case_id == "smoke/G1":
            audit = observed["audit"]
            bronze = observed.get("bronze", [])
            check("archived_physical_count", 3, len(bronze))
            check(
                "archived_bytes",
                fixture["expected"]["bronze_sha256"],
                {item["record_id"]: item["wire_sha256"] for item in bronze},
            )
            check(
                "distinct_broker_deliveries",
                3,
                len({(item["topic"], item["partition"], item["offset"]) for item in bronze}),
            )
            check("one_silver_effect", 1, len(audit["silver_events"]))
            check("one_gold_effect", 1, len(audit["active_gold"]["membership_ids"]))
            invalid = sorted(
                key for key, value in expected["source_dispositions"].items() if value == "invalid"
            )
            check(
                "quarantine_membership",
                invalid,
                sorted(item["record_id"] for item in observed.get("quarantine", [])),
            )
        if case.case_id.startswith("smoke/G3-"):
            check("transaction_audit_present", True, bool(expected["orders"]))
            wanted_status = dict(case.checks)["terminal_status"]
            check(
                "audited_terminal_statuses",
                [wanted_status],
                [order["status"] for order in observed["audit"]["orders"]],
            )
            workflow = observed.get("workflow", [])
            check(
                "public_workflow_steps",
                [
                    "search",
                    "cart",
                    "quote",
                    "confirmation",
                    "checkout",
                    "order",
                    "projection",
                    "gold",
                ],
                [step["operation"] for step in workflow],
            )
            if len(workflow) == 8:
                quote, confirmation, checkout = workflow[2:5]
                check("explicit_confirmation", True, confirmation.get("confirmed"))
                for field in ("quote_id", "cart_id", "cart_version"):
                    value = quote.get(field)
                    check(
                        "quote_binding_present_" + field,
                        True,
                        type(value) is int and value >= 1
                        if field == "cart_version"
                        else isinstance(value, str) and bool(value),
                    )
                    check(
                        "confirmation_binding_" + field, quote.get(field), confirmation.get(field)
                    )
                    check("checkout_binding_" + field, quote.get(field), checkout.get(field))
    return assertions, reconciliation


async def run_cases(invocation, registry, *, allow_test_doubles=False, blocking_reasons=()):
    config = invocation.config
    root = repo_path(config.artifacts.root)
    directory = root / invocation.run_id
    directory.mkdir(parents=True, exist_ok=False)
    started = utc_now()
    selected = expand_suites(invocation.arguments["suite"])
    write_json(
        directory / "case_plan.json",
        {
            "schema_version": 1,
            "cases": [case.__dict__ for case in selected],
            "suite": invocation.arguments["suite"],
            "blocking_reasons": list(blocking_reasons),
        },
    )
    rows, modes = [], set()
    with (directory / "tests.jsonl").open("x", encoding="utf-8") as tests:
        for index, case in enumerate(selected):
            namespace = invocation.namespace + f"-{index:02}"
            if not re.fullmatch(r"bench-[a-z0-9][a-z0-9-]{0,55}", namespace) or re.match(
                r"bench-(dev|live|prod|production)(-|$)", namespace
            ):
                raise DependencyError("case requires an isolated bench namespace")
            case_dir = directory / f"case-{index:02}"
            case_dir.mkdir()
            ctx = {
                "namespace": namespace,
                "run_id": invocation.run_id,
                "case_id": case.case_id,
                "directory": str(case_dir),
                "config": config.model_dump(),
            }
            row = {
                "case_id": case.case_id,
                "owner": case.owner,
                "namespace": namespace,
                "input_fixture_hash": None,
                "started_at": utc_now(),
                "completed_at": None,
                "status": "NOT_RUN",
                "test_mode": "offline",
                "assertions": [],
                "fault_receipt_refs": [],
                "artifact_refs": [],
                "failure_reason": None,
            }
            binding = registry.case(case.case_id)
            try:
                if blocking_reasons:
                    raise DependencyError("; ".join(blocking_reasons))
                if binding is None:
                    raise DependencyError(f"case adapter unavailable; required owner: {case.owner}")
                if binding.mode not in {"real", "stub"} or (
                    binding.mode == "stub" and not allow_test_doubles
                ):
                    raise DependencyError("real evaluation refuses test doubles; no fallback used")
                row["test_mode"] = binding.mode
                modes.add(binding.mode)
                review = None
                if binding.mode == "real":
                    if binding.review_path is None:
                        raise DependencyError("reviewed real audit bindings unavailable")
                    review = validate_review(binding.review_path, namespace, binding.fixture_path)
                    write_json(case_dir / "binding_review.json", review)
                fixture = json.loads(binding.fixture_path.read_text(encoding="utf-8"))
                if fixture["case_id"] != case.case_id or not fixture.get("input"):
                    raise DependencyError("independent case input fixture missing or mismatched")
                fixture["content_sha256"] = content_hash(fixture)
                row["input_fixture_hash"] = fixture["content_sha256"]
                # Persist immutable expected data BEFORE exercising the provider.
                write_json(case_dir / "fixture.json", fixture)
                setup = await owner_call(binding.prepare(copy.deepcopy(ctx)), timeout=900)
                write_json(case_dir / "setup.json", setup)
                validate_setup(setup, ctx, real=binding.mode == "real")
                with (case_dir / "faults.jsonl").open("x", encoding="utf-8") as faults:
                    gate = FaultGate(
                        case, ctx, binding.fault_hooks, lambda item: journal(faults, item)
                    )
                    receipt = await owner_call(
                        binding.exercise(copy.deepcopy(ctx), copy.deepcopy(fixture), gate),
                        timeout=900,
                    )
                write_json(case_dir / "exercise_receipt.json", receipt)
                bound_fixture = bind_runtime_inputs(fixture, receipt)
                write_json(case_dir / "bound_fixture.json", bound_fixture)
                if (case.barrier or case.outage) and not gate.completed:
                    raise DependencyError("required fault barrier/recovery was not executed")
                observed = await owner_call(binding.audit(copy.deepcopy(ctx)), timeout=120)
                write_json(case_dir / "observed.json", observed)
                if observed.get("collection_complete") is not True:
                    raise DependencyError("read-only audit collection incomplete")
                if case.reconcile and observed["audit"]["test_mode"] != binding.mode:
                    raise DependencyError("mixed test modes in audit evidence")
                assertions, reconciliation = check_observation(
                    case, bound_fixture, observed, ctx, review
                )
                row["assertions"] = assertions
                if reconciliation is not None:
                    write_json(case_dir / "correctness.json", reconciliation)
                row["status"] = "PASS" if all(item["passed"] for item in assertions) else "FAIL"
                if row["status"] == "FAIL":
                    row["failure_reason"] = (
                        "independent invariant/contract mismatch; owner review required"
                    )
            except DependencyError as exc:
                row["failure_reason"] = str(exc)
                row["status"] = "NOT_RUN" if row["test_mode"] == "offline" else "INCOMPLETE"
            except Exception as exc:
                # Provider exceptions can contain tokens, DSNs or raw product text.
                row["status"] = "INCOMPLETE"
                row["failure_reason"] = (
                    f"case boundary failed: {type(exc).__name__}; no fallback used"
                )
            row["completed_at"] = utc_now()
            for path in sorted(case_dir.rglob("*")):
                if path.is_file():
                    ref = {
                        "path": path.relative_to(directory).as_posix(),
                        "sha256": file_hash(path),
                    }
                    row["artifact_refs"].append(ref)
                    if path.name == "faults.jsonl" and path.stat().st_size:
                        row["fault_receipt_refs"].append(ref["path"])
            rows.append(row)
            journal(tests, row)
    failed = any(row["status"] == "FAIL" for row in rows)
    complete = all(row["status"] == "PASS" for row in rows)
    not_run = all(row["status"] == "NOT_RUN" for row in rows)
    code = (
        ExitCode.CORRECTNESS_FAILURE
        if failed
        else (ExitCode.COMPLETED if complete else ExitCode.DEPENDENCY_FAILURE)
    )
    mode = "real" if modes == {"real"} else "stub" if modes == {"stub"} else "offline"
    correctness = {
        "schema_version": 1,
        "passed": complete,
        "test_mode": mode,
        "status": "FAIL" if failed else "PASS" if complete else "INCOMPLETE",
        "cases": rows,
        "real_integration_passed": complete and mode == "real",
        "G4_complete": False,
        "limitations": ["P8 only; baseline measurements/P9 not executed"],
    }
    write_json(directory / "correctness.json", correctness)
    reasons = tuple(
        f"{row['case_id']}: {row['failure_reason']}" for row in rows if row["failure_reason"]
    )
    return save_evidence(
        invocation,
        ProviderResult(code, reasons, mode),
        execution={
            "status": "MEASURED" if complete else "NOT_RUN" if not_run else "INCOMPLETE",
            "started_at": started,
            "completed_at": utc_now(),
            "correctness_passed": None if not_run else complete,
            "metrics": [],
        },
    )


def execute_evaluation(invocation, registry):
    from projectctl.cli import preflight

    reasons = preflight(invocation.config)
    if not any(
        registry.case(case.case_id) for case in expand_suites(invocation.arguments["suite"])
    ):
        reasons.append(
            "adapter unavailable: eval run; required owner: Jaineel / case owners; "
            "no selected case bindings registered"
        )
    if registry.binding_failure:
        reasons.append(registry.binding_failure)
    return asyncio.run(run_cases(invocation, registry, blocking_reasons=reasons))


def execute_reconciliation(invocation):
    """Recheck saved immutable case evidence; no provider callback or corrective write."""
    from projectctl.config import ROOT

    source = repo_path(invocation.arguments["run_dir"])
    destination = ROOT / "artifacts/projectctl" / invocation.run_id
    destination.mkdir(parents=True, exist_ok=False)
    started, reports = utc_now(), []
    try:
        manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
        RunManifest.model_validate(manifest)
        if manifest["content_sha256"] != content_hash(manifest):
            raise DependencyError("run manifest missing or changed")
        for ref in manifest["artifacts"]:
            path = (source / ref["path"]).resolve()
            if not path.is_relative_to(source.resolve()) or file_hash(path) != ref["sha256"]:
                raise DependencyError("saved evidence artifact hash mismatch")
        indexed = {ref["path"] for ref in manifest["artifacts"]}
        if manifest["command"] == "eval run":
            if not {"case_plan.json", "tests.jsonl"} <= indexed:
                raise DependencyError("case plan/journal not indexed by run manifest")
            plan = json.loads((source / "case_plan.json").read_text(encoding="utf-8"))
            cases = expand_suites(plan["suite"])
            saved = [
                json.loads(line)
                for line in (source / "tests.jsonl").read_text(encoding="utf-8").splitlines()
            ]
        elif manifest["command"] in {"benchmark run", "benchmark matrix"}:
            from benchmarks.experiment import admission_reconciliation

            if not {"expected.json", "observed.json"} <= indexed:
                raise DependencyError("independent benchmark input/audit projections unavailable")
            expected = json.loads((source / "expected.json").read_text(encoding="utf-8"))
            observed = json.loads((source / "observed.json").read_text(encoding="utf-8"))
            if (
                expected.get("namespace") != manifest["namespace"]
                or observed.get("namespace") != manifest["namespace"]
            ):
                raise DependencyError("benchmark audit namespace differs from run manifest")
            review = None
            if observed.get("test_mode") == "real":
                if "binding_review.json" not in indexed:
                    raise DependencyError("reviewed benchmark audit mapping unavailable")
                review = validate_review(
                    source / "binding_review.json", manifest["namespace"], source / "expected.json"
                )
            report = reconcile_run(expected, observed, binding_review=review)
            if not {"workload_manifest.json", "planned.jsonl", "emissions.jsonl"} <= indexed:
                raise DependencyError("benchmark admission journals unavailable")
            workload = json.loads((source / "workload_manifest.json").read_text(encoding="utf-8"))
            if workload["planned_sha256"] != file_hash(source / "planned.jsonl"):
                raise DependencyError("frozen benchmark schedule hash changed")
            admission = admission_reconciliation(source, workload)
            status = report["status"]
            if admission["invariant_failures"]:
                status = "FAIL"
            elif not admission["passed"] and status == "PASS":
                status = "INCOMPLETE"
            reports.append(
                {
                    "case_id": "benchmark-audit",
                    "status": status,
                    "reconciliation": report,
                    "admission": admission,
                }
            )
            cases, saved = (), []
        else:
            raise DependencyError("command has no independent reconciliation binding")
        if [row["case_id"] for row in saved] != [case.case_id for case in cases]:
            raise DependencyError("saved cases differ from frozen suite expansion")
        for case, row in zip(cases, saved, strict=True):
            report = {"case_id": case.case_id, "status": "INCOMPLETE", "assertions": []}
            try:
                for ref in row["artifact_refs"]:
                    path = (source / ref["path"]).resolve()
                    if (
                        not path.is_relative_to(source.resolve())
                        or file_hash(path) != ref["sha256"]
                    ):
                        raise DependencyError("case raw evidence hash mismatch")
                if row["status"] not in {"PASS", "FAIL"}:
                    raise DependencyError("original case was not complete; rerun required")
                if (case.barrier or case.outage) and not row["fault_receipt_refs"]:
                    raise DependencyError("fault acknowledgement/recovery evidence missing")
                case_dir = source / row["artifact_refs"][0]["path"].split("/")[0]
                fixture = json.loads((case_dir / "fixture.json").read_text(encoding="utf-8"))
                if fixture["content_sha256"] != content_hash(fixture) or (
                    fixture["content_sha256"] != row["input_fixture_hash"]
                ):
                    raise DependencyError("independent fixture hash changed")
                observed = json.loads((case_dir / "observed.json").read_text(encoding="utf-8"))
                receipt = json.loads(
                    (case_dir / "exercise_receipt.json").read_text(encoding="utf-8")
                )
                bound_fixture = bind_runtime_inputs(fixture, receipt)
                if bound_fixture != json.loads(
                    (case_dir / "bound_fixture.json").read_text(encoding="utf-8")
                ):
                    raise DependencyError(
                        "bound expected inputs differ from frozen source/identity receipt"
                    )
                review = None
                if row["test_mode"] == "real":
                    frozen = json.loads(
                        (case_dir / "binding_review.json").read_text(encoding="utf-8")
                    )
                    for ref in frozen["contracts"]:
                        if file_hash(repo_path(ref["path"])) != ref["sha256"]:
                            raise DependencyError(
                                "reviewed binding changed; new owner review required"
                            )
                    review = frozen
                ctx = {"namespace": row["namespace"], "run_id": manifest["run_id"]}
                assertions, reconciliation = check_observation(
                    case, bound_fixture, observed, ctx, review
                )
                report.update(
                    assertions=assertions,
                    reconciliation=reconciliation,
                    status="PASS" if all(a["passed"] for a in assertions) else "FAIL",
                )
            except (DependencyError, OSError, ValueError, KeyError, TypeError) as exc:
                report["reason"] = (
                    str(exc) if isinstance(exc, DependencyError) else type(exc).__name__
                )
            reports.append(report)
    except (DependencyError, OSError, ValueError, KeyError, TypeError) as exc:
        reports.append(
            {
                "status": "INCOMPLETE",
                "reason": str(exc) if isinstance(exc, DependencyError) else type(exc).__name__,
            }
        )
    passed = bool(reports) and all(report["status"] == "PASS" for report in reports)
    failed = any(report["status"] == "FAIL" for report in reports)
    write_json(destination / "correctness.json", {"passed": passed, "cases": reports})
    code = (
        ExitCode.CORRECTNESS_FAILURE
        if failed
        else (ExitCode.COMPLETED if passed else ExitCode.DEPENDENCY_FAILURE)
    )
    return save_evidence(
        invocation,
        ProviderResult(code, ("read-only saved P8 evidence recheck",), "offline"),
        execution={
            "status": "MEASURED" if passed else "INCOMPLETE",
            "started_at": started,
            "completed_at": utc_now(),
            "correctness_passed": passed,
            "metrics": [],
        },
    )
