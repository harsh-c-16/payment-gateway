"""Keep pipeline test scratch files inside the workspace, as the CLI tests do."""

from pathlib import Path
from uuid import uuid4

import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    # The test package's name otherwise shadows the real top-level pipelines package.
    config.option.importmode = "importlib"
    directory = config.rootpath / "artifacts/pytest" / str(uuid4())
    directory.mkdir(parents=True)
    config.inicfg.setdefault("cache_dir", str(directory / "cache"))
    cache = Path(config.getini("cache_dir"))
    if not cache.is_absolute():
        cache = config.rootpath / cache
    cache.mkdir(parents=True, exist_ok=True)
    if config.option.basetemp is None:
        config.option.basetemp = str(directory / "tmp")
