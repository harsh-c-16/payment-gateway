"""Isolated evidence workspace for standalone P8 checks."""

import shutil
from pathlib import Path
from uuid import uuid4

import pytest

import projectctl.artifacts as artifacts
import projectctl.config as config


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    directory = config.rootpath / "artifacts/pytest" / str(uuid4())
    directory.mkdir(parents=True)
    config.inicfg.setdefault("cache_dir", str(directory / "cache"))
    cache = Path(config.getini("cache_dir"))
    if not cache.is_absolute():
        cache = config.rootpath / cache
    cache.mkdir(parents=True, exist_ok=True)
    if config.option.basetemp is None:
        config.option.basetemp = str(directory / "tmp")


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    (tmp_path / "configs").mkdir()
    shutil.copyfile(config.ROOT / "configs/evaluation.yaml", tmp_path / "configs/evaluation.yaml")
    shutil.copyfile(config.ROOT / "uv.lock", tmp_path / "uv.lock")
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(artifacts, "ROOT", tmp_path)
    return tmp_path
