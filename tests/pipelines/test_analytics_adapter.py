"""Provider evidence must not pre-create the CLI's exclusive run directory."""

from contextlib import nullcontext

from infra import analytics
from projectctl.models import ExitCode
from projectctl.providers import Invocation, ProviderRegistry


def test_migration_provider_keeps_its_evidence_outside_cli_owned_directory(tmp_path, monkeypatch):
    calls = []

    class ConnectionDouble:
        def transaction(self):
            return nullcontext()

    tx = ConnectionDouble()
    monkeypatch.setenv("ANALYTICS_DATABASE_URL", "postgresql://explicit-test-double")
    monkeypatch.setattr(analytics.psycopg, "connect", lambda *a, **k: nullcontext(tx))
    monkeypatch.setattr(analytics, "migrate_analytics", lambda value: calls.append(value))
    monkeypatch.setattr(analytics.postgres, "ROOT", tmp_path)
    invocation = Invocation("db migrate", {}, None, "test-m04-evidence", "bench-m04")
    result = analytics.migrate(invocation)
    assert result.code == ExitCode.DEPENDENCY_FAILURE and result.test_mode == "real"
    assert calls == [tx]
    # This is an explicit connection double, not a real migration evidence claim.
    assert (
        tmp_path / "artifacts/infra/analytics/checks/test-m04-evidence/analytics-migration.json"
    ).exists()
    cli_directory = tmp_path / "artifacts/projectctl/test-m04-evidence"
    cli_directory.mkdir(parents=True, exist_ok=False)
    assert "Global db migrate is incomplete" in result.reasons[0]


def test_composition_keeps_existing_environment_providers():
    registry = ProviderRegistry()
    analytics.register(registry)
    assert all(
        registry.missing(action) is None
        for action in ("env up", "env down", "env verify", "db migrate")
    )
