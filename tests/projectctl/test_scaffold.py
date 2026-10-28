import re
import subprocess
from pathlib import Path

import pytest

from projectctl.config import ROOT

DIRECTORIES = """
services/conversation migrations/conversation projectctl benchmarks benchmarks/manual dashboards
shared/telemetry tests/oracles tests/integration tests/conversation tests/projectctl
tests/benchmarks
tests/telemetry tests/contracts contracts/fixtures contracts/fixtures/catalog contracts/evaluation
pipelines/catalog services/catalog analytics/compaction analytics/queries migrations/catalog
tests/catalog tests/analytics contracts/data/catalog contracts/dictionaries/catalog
services/orders services/inventory services/payments shared/outbox migrations/orders
migrations/inventory migrations/payments tests/transactions
pipelines/ingestion pipelines/curation pipelines/gold pipelines/replay pipelines/storage
shared/event_transport shared/local_diagnostics infra migrations/analytics tests/pipelines
contracts/events contracts/dictionaries/events contracts/http shared/contracts configs docs/specs
docs/jaineel docs/decisions .github/workflows data/raw
""".split()


def test_complete_team_scaffold_exists():
    assert all((ROOT / path).is_dir() for path in DIRECTORIES)
    assert len(list((ROOT / "docs" / "specs").glob("[0-9][0-9]_*.md"))) == 11
    assert all(
        name in (ROOT / "docs" / "OWNERSHIP.md").read_text(encoding="utf-8-sig")
        for name in ["Jaineel", "Harsh", "Aditya", "Vichitr"]
    )


@pytest.mark.parametrize(
    "filename",
    [
        "README.md",
        "docs/OWNERSHIP.md",
        "projectctl/README.md",
        "benchmarks/README.md",
        "dashboards/README.md",
        "shared/telemetry/README.md",
    ],
)
def test_owned_and_coordinated_document_links_are_portable_and_resolve(filename):
    path = ROOT / filename
    text = path.read_text(encoding="utf-8-sig")
    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
        if target.startswith(("https://", "http://", "#")):
            continue
        assert not target.startswith("file:"), filename
        assert not Path(target).is_absolute(), filename
        assert (path.parent / target.split("#")[0]).resolve().exists(), target


@pytest.mark.parametrize(
    "path,ignored",
    [
        (".env", True),
        (".env.private", True),
        ("data/raw/flipkart_com-ecommerce_sample.csv", True),
        ("benchmarks/results/probe.json", True),
        ("artifacts/p1/report.json", True),
        (".venv/pyvenv.cfg", True),
        ("data/generated.parquet", True),
        ("data/raw/.gitkeep", False),
        (".env.example", False),
        ("contracts/fixtures/tiny.csv", False),
        ("contracts/fixtures/tiny.json", False),
    ],
)
def test_ignore_rules_keep_secrets_and_results_out_but_allow_fixtures(path, ignored):
    result = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={ROOT.as_posix()}",
            "check-ignore",
            "--no-index",
            "-q",
            path,
        ],
        cwd=ROOT,
        capture_output=True,
    )
    assert result.returncode in {0, 1}, result.stderr
    assert (result.returncode == 0) is ignored


def test_environment_template_uses_frozen_baseline_limits():
    content = (ROOT / ".env.example").read_text()
    values = dict(
        line.split("=", 1) for line in content.splitlines() if line and not line.startswith("#")
    )
    expected = {
        "OUTBOX_POLL_MS": "25",
        "SINK_BATCH_MAX_ROWS": "1",
        "SINK_BATCH_MAX_WAIT_MS": "50",
        "GOLD_PUBLISH_INTERVAL_MS": "250",
        "RESERVATION_TTL_SECONDS": "30",
        "QUOTE_TTL_SECONDS": "60",
        "ASSISTANT_MODE": "fixed",
        "ALLOW_INTENT_LLM": "false",
        "BENCHMARK_MODE": "false",
        "FAULT_INJECTION_ENABLED": "false",
    }
    assert all(values[name] == expected_value for name, expected_value in expected.items())
