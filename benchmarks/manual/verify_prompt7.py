"""Read-only Prompt 7 checkpoint; never starts setup, smoke or performance work.

Reuse the runner's evidence validators. Registration is only an inventory, not
runtime readiness. An absent owner receipt cannot be replaced by local tests.
"""

import argparse
import json
import os
import subprocess
from datetime import UTC, datetime

from benchmarks.performance import CORE_CASES, review_blockers
from projectctl.artifacts import content_hash, file_hash, git_state, write_json
from projectctl.cli import preflight
from projectctl.config import ROOT, InputError, load_config, repo_path
from projectctl.input_pins import review_input_pins
from projectctl.providers import ProviderRegistry


def local_files(config):
    """Observe exact bytes; discovering an owner file does not approve or pin it."""
    paths = {
        "source": config.dataset.source_path,
        "dictionary": config.dataset.dictionary_path,
        "normalized_manifest": config.dataset.canonical_manifest,
        "sku_manifest": config.dataset.sku_manifest,
        "queries": "contracts/fixtures/catalog/queries.json",
        "owner_infrastructure_lock": "infra/images.lock.json",
        "owner_schema_manifest": "contracts/events/manifest.json",
        **{name + "_lock": lock.path for name, lock in config.locks},
    }
    result = {}
    for name, value in paths.items():
        path = repo_path(value) if value else None
        present = path is not None and path.is_file()
        result[name] = {
            "path": value,
            "present": present,
            "raw_sha256": file_hash(path) if present else None,
        }
    return result


def assess(config, registry, *, readiness=None, reuse_connections=None):
    """Inventory prerequisite evidence without invoking any provider or factory."""
    state = git_state()
    checks = []

    def record(name, reasons, **facts):
        checks.append(
            {
                "name": name,
                "status": "NOT_RUN" if reasons else "VERIFIED",
                "reasons": reasons,
                **facts,
            }
        )

    record(
        "code_revision",
        []
        if state.commit and state.dirty is False
        else ["final measurements require a clean committed code revision; preserve existing work"],
        git=state.model_dump(),
    )
    errors = []
    for workload, definition in config.workloads.items():
        if not definition.required:
            continue
        try:
            reasons = preflight(config, workload)
        except InputError as exc:
            reasons = [str(exc)]
            errors.append(str(exc))
        record("preflight/" + workload, reasons)

    pins = review_input_pins()
    record(
        "cross_platform_hash_policy",
        [
            f"{name}: {item['status']}; affected owner hash-policy review required"
            for name, item in pins.items()
            if item["status"] != "VERIFIED"
        ],
        inputs=pins,
    )
    # The current canonical contract requires manually reviewed relevance labels.
    # Do not promote the existing rule-derived file by copying its hash into config.
    record(
        "human_relevance_labels",
        [
            "reviewed human-labelled file/owner evidence unavailable; "
            "rule-derived scores are diagnostic"
        ],
        configured_sha256=config.retrieval.label_sha256,
        certified_metrics=None,
        provenance="docs/harsh/relevance_labels.md",
    )
    reuse = (
        os.environ.get("CATALOG_REUSE_CONNECTIONS", "false")
        if reuse_connections is None
        else reuse_connections
    )
    record(
        "frozen_controls",
        (
            []
            if reuse.strip().lower() == "false"
            else [
                "CATALOG_REUSE_CONNECTIONS must be false; "
                "session reuse is outside the registered matrix"
            ]
        )
        + ([] if config.timing.repetitions == 3 else ["three retained repetitions required"]),
        repetitions=config.timing.repetitions,
        session_reuse_disabled=reuse.strip().lower() == "false",
    )
    inventory = registry.availability()
    missing_actions = [
        name
        for name in (
            "env up",
            "env verify",
            "env reset",
            "db migrate",
            "catalog profile",
            "catalog import",
            "catalog verify",
            "inventory seed",
            "projection wait",
        )
        if not inventory["actions"][name]["registered"]
    ]
    missing_workloads = [
        name
        for name, item in config.workloads.items()
        if item.required and not inventory["workloads"].get(name)
    ]
    missing_cases = sorted(CORE_CASES - set(inventory["cases"]))
    record(
        "owner_bindings",
        ([inventory["binding_failure"]] if inventory["binding_failure"] else [])
        + ["setup adapter unavailable: " + name for name in missing_actions]
        + ["workload binding unavailable: " + name for name in missing_workloads]
        + ["real correctness binding unavailable: " + name for name in missing_cases],
        inventory=inventory,
    )
    # These are successive evidence stages, not executed trials. The existing
    # validator checks actual same-revision resources, inputs and correctness.
    for name, qualified, require_smoke in (
        ("correctness_resources_seed_projection", False, False),
        ("B0_smoke_evidence", False, True),
        ("baseline_diagnosis_before_comparisons", True, True),
    ):
        record(
            name,
            review_blockers(config, readiness, qualified=qualified, require_smoke=require_smoke),
        )

    return {
        "schema_version": 1,
        "checked_at": datetime.now(UTC).isoformat(),
        "status": "INCOMPLETE" if any(c["reasons"] for c in checks) else "PREREQUISITES_VERIFIED",
        "exit_code": 2 if errors else (4 if any(c["reasons"] for c in checks) else 0),
        "test_mode": "offline",
        "config_sha256": content_hash(config.model_dump()),
        "local_files": local_files(config),
        "checks": checks,
        "correctness_passed": None,
        "setup": "NOT_RUN",
        "smoke": "NOT_RUN",
        "performance": "NOT_RUN",
        "B0": {"status": "NOT_RUN", "metrics": None, "frozen_inputs": None},
        "C-BEST": {"status": "NOT_RUN", "selection": None, "metrics": None},
        "real_writes_attempted": False,
        "scope": "Read-only prerequisite inventory; no runtime or measurement certification",
    }


def probe_lock(directory):
    argv = ["uv", "sync", "--locked", "--check"]
    try:
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=30)
        for name in ("stdout", "stderr"):
            (directory / f"lock.{name}.log").write_bytes(getattr(result, name))
        return {
            "argv": argv,
            "exit_code": result.returncode,
            "status": "VERIFIED" if result.returncode == 0 else "NOT_RUN",
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        for name in ("stdout", "stderr"):
            (directory / f"lock.{name}.log").write_bytes(getattr(exc, name, None) or b"")
        return {
            "argv": argv,
            "exit_code": None,
            "status": "NOT_RUN",
            "error_type": type(exc).__name__,
        }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/evaluation.yaml")
    parser.add_argument(
        "--readiness", help="Existing owner-reviewed evidence receipt; never generated here"
    )
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    directory = repo_path(args.out)
    directory.mkdir(parents=True, exist_ok=False)
    try:
        config = load_config(args.config)
        from projectctl.jaineel import register

        registry = ProviderRegistry()
        try:
            register(registry)
        except Exception as exc:
            # Discard partial registrations; never expose exception text/credentials.
            registry = ProviderRegistry()
            registry.binding_failure = "real composition unavailable: " + type(exc).__name__
        result = assess(config, registry, readiness=args.readiness)
        result["config_file"] = {"path": args.config, "sha256": file_hash(repo_path(args.config))}
        write_json(directory / "resolved_config.json", config.model_dump())
    except (InputError, OSError, ValueError) as exc:
        result = {
            "schema_version": 1,
            "status": "INCOMPLETE",
            "exit_code": 2,
            "error_type": type(exc).__name__,
            "performance": "NOT_RUN",
            "correctness_passed": None,
            "real_writes_attempted": False,
        }
    result["application_environment"] = probe_lock(directory)
    if result["application_environment"]["status"] != "VERIFIED" and result["exit_code"] == 0:
        result.update(status="INCOMPLETE", exit_code=4)
    write_json(directory / "readiness.json", result)
    lines = ["# Prompt 7 checkpoint", "", f"Status: {result['status']}; performance: NOT_RUN.", ""]
    for check in result.get("checks", []):
        lines.append(f"- {check['name']}: {check['status']}")
        lines.extend("  - " + reason for reason in check["reasons"])
    lines.extend(
        [
            "",
            "B0 inputs are not frozen. C-BEST is not selected.",
            "Use the canonical runbook for setup and measurements after the gates close.",
        ]
    )
    (directory / "checkpoint.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "exit_code": result["exit_code"],
                "status": result["status"],
                "performance": "NOT_RUN",
                "evidence_dir": args.out,
            }
        )
    )
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
