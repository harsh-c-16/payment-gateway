"""Rehearse P10 in an isolated clone; copy only explicitly indexed evidence and source."""

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

from benchmarks.dataset_checks import SOURCE_SHA256, inspect_source
from benchmarks.reporting import build_report
from projectctl.artifacts import file_hash, write_json
from projectctl.config import ROOT, repo_path


def setup_commands(namespace):
    output = f"artifacts/catalog/{namespace}"
    source = "data/raw/flipkart_com-ecommerce_sample.csv"
    return [
        ["env", "up", "--profile", "local4c8g"],
        ["env", "verify", "--profile", "local4c8g"],
        ["db", "migrate", "--namespace", namespace],
        ["contracts", "check", "--all"],
        [
            "catalog",
            "profile",
            "--source",
            source,
            "--rules",
            "flipkart-v1",
            "--out",
            "artifacts/catalog/profile",
        ],
        [
            "catalog",
            "import",
            "--source",
            source,
            "--rules",
            "flipkart-v1",
            "--load-mode",
            "row",
            "--namespace",
            namespace,
            "--out",
            output,
        ],
        [
            "catalog",
            "verify",
            "--manifest",
            output + "/normalized_manifest.json",
            "--namespace",
            namespace,
        ],
        [
            "inventory",
            "seed",
            "--sku-manifest",
            output + "/sku_manifest.json",
            "--namespace",
            namespace,
            "--profile",
            "performance",
            "--seed",
            "42",
        ],
        [
            "projection",
            "wait",
            "--namespace",
            namespace,
            "--sku-manifest",
            output + "/sku_manifest.json",
            "--timeout-seconds",
            "120",
        ],
        ["fixtures", "build", "--config", "configs/evaluation.yaml", "--seed", "42"],
        ["eval", "run", "--suite", "contracts,data,smoke", "--config", "configs/evaluation.yaml"],
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--out", required=True)
    parser.add_argument("--revision", required=True, help="committed revision to rehearse")
    parser.add_argument("--matrix-results", required=True)
    parser.add_argument("--source", type=Path, help="explicit unchanged CSV; no hidden file reuse")
    parser.add_argument(
        "--adapter-module", help="explicit reviewed adapter module in that revision"
    )
    args = parser.parse_args(argv)
    destination = repo_path(args.out)
    if not destination.is_relative_to(ROOT / "artifacts"):
        parser.error("--out must be a fresh directory inside artifacts/")
    destination.mkdir(parents=True, exist_ok=False)
    checkout = destination / "checkout"
    namespace = "bench-p10-" + uuid4().hex
    # Explicit allowlist: no .env, provider keys, adapter selection or test DB inherited.
    environment = {
        k: v
        for k, v in os.environ.items()
        if k.upper()
        in {
            "PATH",
            "SYSTEMROOT",
            "WINDIR",
            "COMSPEC",
            "PATHEXT",
            "TEMP",
            "TMP",
            "USERPROFILE",
            "LOCALAPPDATA",
            "APPDATA",
            "PROGRAMFILES",
            "PROGRAMFILES(X86)",
            "SYSTEMDRIVE",
        }
    }
    environment.update(PYTHONIOENCODING="utf-8", ASSISTANT_MODE="fixed", ALLOW_INTENT_LLM="false")
    if args.adapter_module:
        environment["PROJECTCTL_ADAPTER_MODULE"] = args.adapter_module
    checks = []

    def run(label, command, *, cwd, timeout=600):
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=timeout,
            )
            stdout, stderr, code = result.stdout, result.stderr, result.returncode
        except (OSError, subprocess.TimeoutExpired) as exc:
            stdout, stderr, code = "", type(exc).__name__, 4
        (destination / f"{label}.stdout.txt").write_text(stdout, encoding="utf-8")
        (destination / f"{label}.stderr.txt").write_text(stderr, encoding="utf-8")
        row = {
            "label": label,
            "command": command,
            "cwd": str(cwd),
            "exit_code": code,
            "status": "PASS" if code == 0 else "INCOMPLETE",
        }
        write_json(destination / f"{label}.command.json", row)
        checks.append(row)
        print(f"{label}: exit {code}", flush=True)
        return code

    clone_ok = (
        run(
            "clone",
            [
                "git",
                "clone",
                "--no-hardlinks",
                "--no-checkout",
                "--no-tags",
                str(ROOT),
                str(checkout),
            ],
            cwd=ROOT,
        )
        == 0
    )
    checkout_ok = (
        clone_ok
        and run("checkout", ["git", "checkout", "--detach", args.revision], cwd=checkout) == 0
    )
    install_ok = (
        checkout_ok
        and run(
            "locked-install",
            [
                "uv",
                "sync",
                "--locked",
                "--python",
                "3.11",
                "--cache-dir",
                str(destination / "uv-cache"),
            ],
            cwd=checkout,
        )
        == 0
    )
    python = checkout / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
    original = build_report(args.matrix_results)
    copied = []
    for ref in original["evidence_index"] if checkout_ok else []:
        source, target = repo_path(ref["path"]), checkout / ref["path"]
        if file_hash(source) != ref["sha256"]:
            raise ValueError("input evidence changed during export")
        if target.exists():
            if file_hash(target) != ref["sha256"]:
                raise ValueError("indexed code/fixture differs from clean revision")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        copied.append(ref)
    source_ok = False
    if checkout_ok and args.source:
        if file_hash(args.source) != SOURCE_SHA256:
            raise ValueError("explicit source CSV is not the unchanged file08 input")
        target = checkout / "data/raw/flipkart_com-ecommerce_sample.csv"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.source, target)
        source_ok = file_hash(target) == SOURCE_SHA256
        write_json(destination / "source-check.json", inspect_source(target))
    prerequisite = bool(install_ok and source_ok)
    for index, command in enumerate(setup_commands(namespace)):
        label = f"setup-{index:02}"
        if prerequisite:
            prerequisite = (
                run(label, [str(python), "-m", "projectctl", *command], cwd=checkout) == 0
            )
        else:
            checks.append(
                {
                    "label": label,
                    "command": [str(python), "-m", "projectctl", *command],
                    "exit_code": None,
                    "status": "NOT_RUN",
                    "reason": "setup prerequisite unavailable; no provider substitution",
                }
            )
    stable, detected = False, False
    if install_ok:
        # Independent checks retain actual provider failures after the setup chain blocks.
        run(
            "contracts",
            [str(python), "-m", "projectctl", "contracts", "check", "--all"],
            cwd=checkout,
        )
        run(
            "data-smoke",
            [
                str(python),
                "-m",
                "projectctl",
                "eval",
                "run",
                "--suite",
                "contracts,data,smoke",
                "--config",
                "configs/evaluation.yaml",
            ],
            cwd=checkout,
        )
        codes = [
            run(
                f"report-{n}",
                [
                    str(python),
                    "-m",
                    "projectctl",
                    "report",
                    "build",
                    "--matrix-results",
                    args.matrix_results,
                    "--out",
                    f"artifacts/p10-rebuild-{n}",
                ],
                cwd=checkout,
            )
            for n in (1, 2)
        ]
        reports = [checkout / f"artifacts/p10-rebuild-{n}/report.json" for n in (1, 2)]
        stable = (
            all(p.is_file() for p in reports) and reports[0].read_bytes() == reports[1].read_bytes()
        )
        if stable:
            stable = json.loads(reports[0].read_text(encoding="utf-8")) == original
        if original["runs"]:
            # Only this new disposable copy is damaged. Original and exported evidence stay intact.
            record = original["runs"][0]
            copied_run = checkout / "artifacts/p10-corruption/run"
            shutil.copytree(checkout / record["evidence_dir"], copied_run)
            victim = (copied_run / "summary.json").resolve()
            if not victim.is_relative_to((checkout / "artifacts/p10-corruption").resolve()):
                raise ValueError("disposable deletion target escaped its directory")
            victim.unlink()
            data = json.loads((checkout / args.matrix_results).read_text(encoding="utf-8"))
            next(r for r in data["runs"] if r["run_id"] == record["run_id"])["evidence_dir"] = (
                copied_run.relative_to(checkout).as_posix()
            )
            source_results = checkout / args.matrix_results
            data["plan"] = str(
                (source_results.parent / data["plan"]).relative_to(checkout)
            ).replace("\\", "/")
            # Keep the plan beside this disposable result, as native matrix bundles require.
            bad_dir = checkout / "artifacts/p10-corruption"
            shutil.copyfile(checkout / data["plan"], bad_dir / "plan.json")
            data["plan"] = "plan.json"
            write_json(bad_dir / "results.json", data)
            code = run(
                "corruption",
                [
                    str(python),
                    "-m",
                    "projectctl",
                    "report",
                    "build",
                    "--matrix-results",
                    "artifacts/p10-corruption/results.json",
                    "--out",
                    "artifacts/p10-corruption/refused",
                ],
                cwd=checkout,
            )
            detected = (
                code == 4
                and not json.loads((bad_dir / "refused/report.json").read_text(encoding="utf-8"))[
                    "runs"
                ]
            )
        else:
            codes = []
    else:
        codes = []
    summary = {
        "schema_version": 1,
        "namespace": namespace,
        "revision": args.revision,
        "checks": checks,
        "locked_install_passed": bool(install_ok),
        "source_sha256": SOURCE_SHA256 if source_ok else None,
        "report_rebuild_identical": stable,
        "report_exit_codes": codes,
        "missing_evidence_detected": detected,
        "exported_evidence": copied,
        "real_setup_status": "PASS" if prerequisite else "INCOMPLETE",
        "performance_metric_trace": "NOT_RUN"
        if not any(r["metrics"] for r in original["runs"])
        else "REVIEW_REQUIRED",
        "teammate_reproduction": "NOT_RUN",
        "next_milestone_started": False,
    }
    write_json(destination / "checks.json", summary)
    write_json(
        destination / "evidence-index.json",
        {
            "artifacts": [
                {"path": p.relative_to(destination).as_posix(), "sha256": file_hash(p)}
                for p in sorted(destination.iterdir())
                if p.is_file()
            ]
        },
    )
    print(
        json.dumps(
            {
                "evidence_dir": args.out,
                "report_rebuild_identical": stable,
                "missing_evidence_detected": detected,
                "real_setup_status": summary["real_setup_status"],
            }
        ),
        flush=True,
    )
    return 0 if prerequisite and stable and detected else 4


if __name__ == "__main__":
    raise SystemExit(main())
