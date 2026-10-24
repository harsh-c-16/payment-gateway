"""Contract tests are offline and use only explicitly labelled doubles."""

import json
from uuid import uuid4

import pytest

from shared.contracts.common import RequestContext

from .provisional import ROOT, uid


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    run_directory = config.rootpath / "artifacts" / "pytest" / str(uuid4())
    run_directory.mkdir(parents=True)
    config.inicfg.setdefault("cache_dir", str(run_directory / "cache"))
    if config.option.basetemp is None:
        config.option.basetemp = str(run_directory / "tmp")


@pytest.fixture
def context():
    return RequestContext(
        namespace="bench-p2",
        run_id=uid(10),
        user_id="p2-user",
        correlation_id=uid(11),
        request_id=uid(1),
        session_id=uid(2),
        trace_id="p2-trace",
    )


@pytest.fixture
def pairs():
    source = json.loads((ROOT / "contracts/fixtures/p2/pairs.json").read_text(encoding="utf-8"))
    assert source["provisional"] and source["synthetic"] and source["test_mode"] == "stub"
    return {pair["name"]: pair for pair in source["pairs"]}
