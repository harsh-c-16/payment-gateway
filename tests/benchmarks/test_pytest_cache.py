"""Reproduce denied Windows cache rename without changing ACLs or deleting evidence."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "test",
    [
        "tests/projectctl/test_artifacts.py::test_file_hash_covers_exact_bytes",
        "tests/contracts/test_contracts.py::test_misspelled_required_field_is_rejected",
        "tests/oracles/test_dataset.py::test_missing_source_is_not_run",
        "tests/benchmarks/test_metrics.py::test_manual_nearest_rank_examples",
    ],
)
def test_standalone_suites_work_when_cache_directory_rename_is_denied(test):
    program = """
import pathlib
import sys
import pytest
original = pathlib.Path.rename
def denied(self, target):
    if self.name.startswith("pytest-cache-files-"):
        raise PermissionError("explicit Windows cache-rename failure double")
    return original(self, target)
pathlib.Path.rename = denied
raise SystemExit(pytest.main([sys.argv[1], "-q", "-W", "error::pytest.PytestCacheWarning"]))
"""
    result = subprocess.run(
        [sys.executable, "-c", program, test],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "passed" in result.stdout
