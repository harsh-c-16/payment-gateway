"""Infrastructure composition plus only Vichitr's analytics migration provider."""

import json
import os

import psycopg

from infra import postgres, streaming
from pipelines.ingestion.receipts import migrate_analytics
from projectctl.models import ExitCode
from projectctl.providers import ProviderResult


def migrate(invocation):
    try:
        url = os.environ.get("ANALYTICS_DATABASE_URL") or postgres.database_url(
            "analytics", postgres.credentials()
        )
        with psycopg.connect(url, connect_timeout=5) as tx, tx.transaction():
            migrate_analytics(tx)
        out = postgres.ROOT / "artifacts/infra/analytics/checks" / invocation.run_id
        out.mkdir(parents=True, exist_ok=False)
        (out / "analytics-migration.json").write_text(
            json.dumps(
                {
                    "owner": "Vichitr",
                    "analytics_capture_migration": "APPLIED",
                    "namespace_argument": invocation.namespace,
                    "scope": "analytics database schema; no namespace data reset",
                    "other_service_migrations": "NOT_RUN",
                    "outbox_migration": "NOT_RUN",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return ProviderResult(
            ExitCode.DEPENDENCY_FAILURE,
            (
                "Analytics capture migration applied. Global db migrate is incomplete: "
                "other service/outbox migration providers still require owner composition.",
                f"Evidence: {out.relative_to(postgres.ROOT).as_posix()}/analytics-migration.json",
            ),
            "real",
        )
    except (psycopg.Error, postgres.SetupError, RuntimeError, OSError) as exc:
        return ProviderResult(ExitCode.DEPENDENCY_FAILURE, (type(exc).__name__,), "real")


def register(registry):
    streaming.register(registry)
    registry.register("db migrate", migrate)
