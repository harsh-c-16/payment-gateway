"""Only CLI tests use this isolated filesystem; no fake services enter application code."""

import shutil
from pathlib import Path
from uuid import uuid4

import pytest

import projectctl.artifacts as artifacts
import projectctl.config as config


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    """Isolate disposable P1 state from Windows caches owned by another account."""
    run_directory = config.rootpath / "artifacts" / "pytest" / str(uuid4())
    run_directory.mkdir(parents=True)
    # Configure before pytest's cache/tmp plugins initialize. Preserve explicit overrides.
    config.inicfg.setdefault("cache_dir", str(run_directory / "cache"))
    cache = Path(config.getini("cache_dir"))
    if not cache.is_absolute():
        cache = config.rootpath / cache
    # Avoid pytest's temporary-directory rename, which OneDrive can deny on Windows.
    cache.mkdir(parents=True, exist_ok=True)
    if config.option.basetemp is None:
        config.option.basetemp = str(run_directory / "tmp")


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    (tmp_path / "configs").mkdir()
    for name in ("evaluation.yaml", "core_matrix.yaml"):
        shutil.copyfile(config.ROOT / "configs" / name, tmp_path / "configs" / name)
    shutil.copyfile(config.ROOT / "uv.lock", tmp_path / "uv.lock")
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(artifacts, "ROOT", tmp_path)
    return tmp_path
