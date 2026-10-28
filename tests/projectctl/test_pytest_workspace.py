"""Regression coverage for the Windows temp/cache setup failure reported after P1."""

import os
import subprocess
import sys

import pytest

from projectctl.config import ROOT


@pytest.mark.parametrize("explicit_paths", [False, True])
def test_pytest_works_with_an_unusable_global_temp_root(tmp_path, explicit_paths):
    # A file cannot contain pytest-of-<user>. Using it as the global temp root
    # reproduces inaccessible default temp storage without changing any Windows ACLs.
    blocked = tmp_path / "unusable-global-temp"
    blocked.write_text("not a directory", encoding="utf-8")
    environment = os.environ.copy()
    environment["PYTEST_DEBUG_TEMPROOT"] = str(blocked)
    environment["PYTHONIOENCODING"] = "utf-8"
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/projectctl/test_artifacts.py::test_file_hash_covers_exact_bytes",
        "-v",
        "-W",
        "error::pytest.PytestCacheWarning",
    ]
    if explicit_paths:
        command.extend(
            [
                "--basetemp",
                str(tmp_path / "explicit-temp"),
                "-o",
                f"cache_dir={tmp_path / 'explicit-cache'}",
            ]
        )
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout
    if explicit_paths:
        assert list((tmp_path / "explicit-temp").rglob("raw.csv"))
        assert (tmp_path / "explicit-cache" / "v" / "cache" / "nodeids").is_file()
    else:
        assert "cachedir: artifacts/pytest/" in result.stdout.replace("\\", "/")
