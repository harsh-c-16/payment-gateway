"""Reset safety and owner handoff checks use explicit SQL/lifecycle doubles."""

import asyncio
from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace

import pytest

from pipelines.ingestion import adapters, lifecycle
from tests.pipelines.test_analytics_deployment import context


class ResetDatabase:
    def __init__(self, blocked=None):
        self.blocked, self.deletes = blocked, []

    @contextmanager
    def connect(self):
        yield self

    @contextmanager
    def transaction(self):
        yield

    def execute(self, statement, values=()):
        text = statement if isinstance(statement, str) else statement.as_string()
        if text.startswith("DELETE"):
            assert values == ("bench-adapter",)
            self.deletes.append(text)
        row = (1,) if self.blocked and self.blocked in text else None
        return SimpleNamespace(fetchone=lambda: row, rowcount=1)


@pytest.mark.parametrize("namespace", ["dev", "bench-live", "replay-other", "bench-production-x"])
def test_reset_rejects_protected_namespace_before_sql(namespace):
    with pytest.raises(ValueError):
        lifecycle.reset_namespace(None, namespace, quiescent=True, evaluation_accepted=True)


@pytest.mark.parametrize("stopped,accepted", [(False, True), (True, False), (1, True), (True, 1)])
def test_reset_requires_explicit_quiescence_and_acceptance(stopped, accepted):
    with pytest.raises(ValueError):
        lifecycle.reset_namespace(
            None, "bench-adapter", quiescent=stopped, evaluation_accepted=accepted
        )


@pytest.mark.parametrize(
    "blocked", ["replay_inputs", "captured_at>", "manifest->>", "published_at"]
)
def test_retention_replay_and_pending_outbox_block_all_deletes(monkeypatch, blocked):
    database = ResetDatabase(blocked)
    monkeypatch.setattr(lifecycle, "one", lambda *args: {"locked": True})
    with pytest.raises(ValueError):
        lifecycle.reset_namespace(
            database, "bench-adapter", quiescent=True, evaluation_accepted=True
        )
    assert database.deletes == []


def test_explicit_reset_uses_only_scoped_deletes_and_retains_files(monkeypatch):
    database = ResetDatabase()
    monkeypatch.setattr(lifecycle, "one", lambda *args: {"locked": True})
    result = lifecycle.reset_namespace(
        database, "bench-adapter", quiescent=True, evaluation_accepted=True
    )
    assert len(database.deletes) == len(lifecycle.TABLES)
    assert all("WHERE namespace=%s" in query for query in database.deletes)
    assert result["immutable_files_retained"] is True
    assert not any("replay_jobs" in query or "TRUNCATE" in query for query in database.deletes)


@pytest.mark.parametrize("missing,unfinished", [(True, 0), (False, 1)])
def test_drain_never_treats_missing_lag_or_pending_work_as_drained(
    monkeypatch, missing, unfinished
):
    deployment = SimpleNamespace(check_context=lambda context: None)
    callbacks = adapters.AnalyticsCallbacks(None, lambda: None, deployment, bootstrap="double")
    lag = SimpleNamespace(
        series=("partition",),
        read_sync=lambda: {} if missing else {"partition": SimpleNamespace(value=0)},
    )
    monkeypatch.setattr(callbacks, "sources_factory", lambda context: SimpleNamespace(lag=lag))
    monkeypatch.setattr(callbacks, "_unfinished", lambda *args: unfinished)
    with pytest.raises(TimeoutError):
        asyncio.run(callbacks.drain(context(), 0.01))


def test_drain_requires_offsets_gold_and_outbox_to_be_complete(monkeypatch):
    callbacks = adapters.AnalyticsCallbacks(
        None, lambda: None, SimpleNamespace(check_context=lambda context: None), bootstrap="double"
    )
    lag = SimpleNamespace(
        series=("partition",), read_sync=lambda: {"partition": SimpleNamespace(value=0)}
    )
    monkeypatch.setattr(callbacks, "sources_factory", lambda context: SimpleNamespace(lag=lag))
    monkeypatch.setattr(callbacks, "_unfinished", lambda *args: 0)
    assert asyncio.run(callbacks.drain(context(), 1)) is None


def test_runner_registration_is_lazy_and_rejects_changed_run_parameters():
    runner = adapters.AnalyticsRunner(
        None, lambda: None, bootstrap="double", worker_memory_mib=384, worker_cpu_cores=0.5
    )
    hooks = runner.owner_callbacks(
        seed_audit=lambda context: None,
        independent_audit=lambda *args: None,
        resource_factory=lambda context: (),
    )
    assert hooks.fresh_namespace == runner.fresh_namespace and runner.runs == {}
    first = runner.for_run(context())
    assert runner.for_run(context()) is first
    changed = context(partitions=3, consumers=3)
    with pytest.raises(ValueError, match="parameters changed"):
        runner.for_run(changed)


def test_migration_participant_succeeds_locally_without_claiming_global_setup(
    monkeypatch, tmp_path
):
    from infra import analytics
    from projectctl.models import ExitCode
    from projectctl.providers import Invocation

    database = ResetDatabase()
    monkeypatch.setenv("ANALYTICS_DATABASE_URL", "explicit-sql-double")
    monkeypatch.setattr(analytics.psycopg, "connect", lambda *args, **kwargs: database.connect())
    monkeypatch.setattr(analytics, "migrate_analytics", lambda tx: None)
    monkeypatch.setattr(analytics.postgres, "ROOT", tmp_path)
    invocation = Invocation("db migrate", {}, None, "fixture", "bench-adapter")
    assert analytics.migrate_action(invocation).code == ExitCode.COMPLETED
    assert analytics.migrate_action(invocation).code == ExitCode.COMPLETED
    assert analytics.migrate(invocation).code == ExitCode.DEPENDENCY_FAILURE


def test_business_gold_export_retains_exact_money_and_table_identity(monkeypatch):
    from projectctl.artifacts import canonical_json

    @contextmanager
    def read_connect():
        yield SimpleNamespace(execute=lambda sql: SimpleNamespace(fetchone=lambda: ("on",)))

    manifest = SimpleNamespace(
        generation=1,
        files=[SimpleNamespace(schema_name="daily_conversion")],
        model_dump=lambda **kwargs: {"namespace": "bench-adapter", "generation": 1},
    )
    monkeypatch.setattr(adapters, "active_manifest", lambda *args: manifest)
    monkeypatch.setattr(adapters, "iter_membership", lambda *args: ["event-double"])
    monkeypatch.setattr(adapters, "iter_verified", lambda *args: [{"amount": Decimal(2**70)}])
    result = adapters.AnalyticsSources(read_connect, None, None).active("bench-adapter")
    assert result["rows"] == result["tables"]["daily_conversion"] == [{"amount": 2**70}]
    assert str(2**70).encode() in canonical_json(result)


def test_three_worker_observer_preserves_distinct_series(monkeypatch):
    deployment = SimpleNamespace(workers=("worker-0", "worker-1", "worker-2"))
    callbacks = adapters.AnalyticsCallbacks(None, lambda: None, deployment, bootstrap="double")
    monkeypatch.setattr(adapters, "RuntimeObserver", lambda targets, **kwargs: targets)
    targets = callbacks.observer_factory(resource_factory=lambda context: ())
    keys = [series.key for target in targets for series in target.series]
    assert len(keys) == len(set(keys)) == 12
