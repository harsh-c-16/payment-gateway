"""Retain the P9 checkpoint: real commands fail visibly when handoffs are absent."""

import json
import subprocess
import sys
from uuid import uuid4

from projectctl.artifacts import content_hash, file_hash, write_json
from projectctl.config import ROOT


def main():
    root = ROOT / "artifacts/p9" / str(uuid4())
    root.mkdir(parents=True)
    commands = [
        ["contracts", "check", "--all"],
        [
            "eval",
            "run",
            "--suite",
            "correctness,smoke,T-10,T-11",
            "--config",
            "configs/evaluation.yaml",
        ],
        [
            "benchmark",
            "run",
            "--workload",
            "W-PIPE",
            "--variants",
            "B0",
            "--repetitions",
            "1",
            "--smoke",
            "--config",
            "configs/evaluation.yaml",
        ],
        [
            "benchmark",
            "run",
            "--workload",
            "W-PIPE",
            "--variants",
            "B0",
            "--repetitions",
            "1",
            "--config",
            "configs/evaluation.yaml",
        ],
        [
            "benchmark",
            "matrix",
            "--matrix",
            "configs/core_matrix.yaml",
            "--config",
            "configs/evaluation.yaml",
        ],
    ]
    checks = []
    for index, args in enumerate(commands):
        command = [sys.executable, "-m", "projectctl", *args]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        (root / f"{index}.stdout.json").write_text(result.stdout, encoding="utf-8")
        (root / f"{index}.stderr.txt").write_text(result.stderr, encoding="utf-8")
        output = json.loads(result.stdout)
        rows = output.get("runs", [output])
        refs = []
        for row in rows:
            directory = ROOT / row["evidence_dir"]
            manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
            assert manifest["content_sha256"] == content_hash(manifest)
            if args[0] == "benchmark":
                assert manifest["started_at"] is None
            if args[0] == "eval":
                cases = [
                    json.loads(line)
                    for line in (directory / "tests.jsonl").read_text(encoding="utf-8").splitlines()
                ]
                assert cases and all(case["status"] == "NOT_RUN" for case in cases)
            assert all(m["value"] is None and m["status"] == "NOT_RUN" for m in row["metrics"])
            for ref in manifest["artifacts"]:
                assert file_hash(directory / ref["path"]) == ref["sha256"]
            refs.append(row["evidence_dir"])
        checks.append(
            {
                "command": command,
                "actual_exit": result.returncode,
                "expected_exit": 4,
                "matched": result.returncode == 4,
                "run_count": len(rows),
                "evidence_directories": refs,
            }
        )
    report = {
        "schema_version": 1,
        "checks": checks,
        "checkpoint": "owner harness verified; real measurement prerequisites unavailable",
        "real_integration": "NOT_RUN",
        "performance": "NOT_RUN",
        "C-BEST": None,
        "matrix_launches": 1,
        "passed": all(c["matched"] for c in checks),
    }
    write_json(root / "checks.json", report)
    print(
        json.dumps({"evidence_dir": root.relative_to(ROOT).as_posix(), "passed": report["passed"]})
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
