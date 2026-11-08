"""Infrastructure composition plus only Vichitr's analytics migration provider."""

import json
import os

import psycopg

from infra import postgres, streaming
from pipelines.ingestion.receipts import migrate_analytics
from projectctl.models import ExitCode
from projectctl.providers import ProviderResult


def migrate_action(invocation):
    try:
        url = os.environ.get("ANALYTICS_DATABASE_URL") or postgres.database_url(
            "analytics", postgres.credentials()
        )
        with psycopg.connect(url, connect_timeout=5) as tx, tx.transaction():
            migrate_analytics(tx)
        out = postgres.ROOT / "artifacts/infra/analytics/checks" / invocation.run_id
        out.mkdir(parents=True, exist_ok=True)
        (out / "analytics-migration.json").write_text(
            json.dumps(
                {
                    "owner": "Vichitr",
                    "analytics_capture_migration": "APPLIED",
                    "analytics_migration_versions": list(range(1, 11)),
                    "namespace_argument": invocation.namespace,
                    "scope": "analytics database schema; no namespace data reset",
                    "other_service_migrations": "NOT_RUN",
                    "outbox_migration": "APPLIED; analytics database only",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return ProviderResult(
            ExitCode.COMPLETED,
            (
                "Analytics migrations applied; only analytics database changed.",
                f"Evidence: {out.relative_to(postgres.ROOT).as_posix()}/analytics-migration.json",
            ),
            "real",
        )
    except (psycopg.Error, postgres.SetupError, RuntimeError, OSError) as exc:
        return ProviderResult(ExitCode.DEPENDENCY_FAILURE, (type(exc).__name__,), "real")


def migrate(invocation):
    result = migrate_action(invocation)
    if result.code != ExitCode.COMPLETED:
        return result
    return ProviderResult(
        ExitCode.DEPENDENCY_FAILURE,
        (*result.reasons, "Global db migrate still requires other owners' migration participants."),
        "real",
    )


def register(registry):
    streaming.register(registry)
    registry.register("db migrate", migrate)
