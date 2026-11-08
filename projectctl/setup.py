"""Global migration coordination delegates to each owner's explicit participant."""

import os
import re
from dataclasses import dataclass

from projectctl.models import ExitCode
from projectctl.providers import ProviderResult

DATABASE_OWNERS = ("conversation", "catalog", "orders", "inventory", "payments", "analytics")


def migrate_catalog(invocation):
    """Delegate to Harsh's migration machinery using only his database binding."""
    import psycopg

    from pipelines.catalog.adapter import database_url
    from pipelines.catalog.migrate import migrate_catalog as migrate

    try:
        with psycopg.connect(database_url(), connect_timeout=5) as tx:
            migrate(tx)
    except Exception as exc:
        return ProviderResult(
            ExitCode.DEPENDENCY_FAILURE,
            ("catalog migration failed: " + type(exc).__name__,),
            "real",
        )
    return ProviderResult(ExitCode.COMPLETED, ("Catalogue owner migrations applied",), "real")


def migrate_conversation(invocation):
    """The concrete M1 participant; success applies only to conversation_db."""
    from services.conversation.database import Database
    from services.conversation.errors import ServiceError

    url = os.environ.get("CONVERSATION_DATABASE_URL")
    if not url:
        return ProviderResult(
            ExitCode.DEPENDENCY_FAILURE,
            ("CONVERSATION_DATABASE_URL required for M1 migrations",),
            "real",
        )
    try:
        database = Database(url)
        database.migrate()
        database.ready()
    except (ServiceError, OSError, ValueError) as exc:
        return ProviderResult(
            ExitCode.DEPENDENCY_FAILURE, ("M1 migration failed: " + type(exc).__name__,), "real"
        )
    return ProviderResult(
        ExitCode.COMPLETED,
        ("Conversation migrations applied/verified; no other database changed",),
        "real",
    )


class MigrationCoordinator:
    def __init__(self, participants):
        self.participants = {"conversation": migrate_conversation, **participants}
        if set(self.participants) - set(DATABASE_OWNERS) or any(
            not callable(callback) for callback in self.participants.values()
        ):
            raise ValueError("explicit known database migration participants required")

    def __call__(self, invocation):
        missing = set(DATABASE_OWNERS) - self.participants.keys()
        if missing:
            return ProviderResult(
                ExitCode.DEPENDENCY_FAILURE,
                tuple("migration participant unavailable: " + n for n in sorted(missing)),
                "real",
            )
        completed = []
        for name in DATABASE_OWNERS:
            try:
                result = self.participants[name](invocation)
            except Exception as exc:
                return ProviderResult(
                    ExitCode.DEPENDENCY_FAILURE,
                    (*completed, name + " migration failed: " + type(exc).__name__),
                    "real",
                )
            if (
                not isinstance(result, ProviderResult)
                or result.test_mode != "real"
                or not isinstance(result.code, ExitCode)
            ):
                return ProviderResult(
                    ExitCode.DEPENDENCY_FAILURE,
                    (*completed, name + " migration lacks real evidence"),
                    "real",
                )
            if result.code != ExitCode.COMPLETED:
                return ProviderResult(
                    result.code,
                    (*completed, name + " migration incomplete", *result.reasons),
                    "real",
                )
            completed.append(name + " migration completed")
        return ProviderResult(ExitCode.COMPLETED, tuple(completed), "real")


@dataclass(frozen=True)
class ResetParticipant:
    """Owner preflight is read-only; apply retains that owner's retention/locking guards."""

    preflight: object
    apply: object

    def __post_init__(self):
        if not callable(self.preflight) or not callable(self.apply):
            raise ValueError("reset needs explicit preflight and apply callbacks")


class ResetCoordinator:
    """No implicit reset and no partial deletion when a known participant is missing.

    Cross-database apply is not atomic. A late failure reports the completed
    participants and stops; retries must revalidate owner-local invariants.
    """

    def __init__(self, participants):
        if set(participants) - set(DATABASE_OWNERS) or any(
            not isinstance(p, ResetParticipant) for p in participants.values()
        ):
            raise ValueError("known owner reset participants required")
        self.participants = dict(participants)

    def __call__(self, invocation):
        if not re.fullmatch(r"bench-[a-z0-9][a-z0-9-]{0,55}", invocation.namespace) or re.match(
            r"bench-(dev|live|prod|production)(-|$)", invocation.namespace
        ):
            return ProviderResult(
                ExitCode.BAD_INPUT, ("isolated bench namespace required",), "real"
            )
        missing = set(DATABASE_OWNERS) - self.participants.keys()
        if missing:
            return ProviderResult(
                ExitCode.DEPENDENCY_FAILURE,
                tuple("reset participant unavailable: " + n for n in sorted(missing)),
                "real",
            )
        completed = []
        for phase in ("preflight", "apply"):
            for name in DATABASE_OWNERS:
                try:
                    result = getattr(self.participants[name], phase)(invocation)
                except Exception as exc:
                    result = ProviderResult(
                        ExitCode.DEPENDENCY_FAILURE, (type(exc).__name__,), "real"
                    )
                if (
                    not isinstance(result, ProviderResult)
                    or result.test_mode != "real"
                    or not isinstance(result.code, ExitCode)
                ):
                    return ProviderResult(
                        ExitCode.DEPENDENCY_FAILURE,
                        (*completed, name + " reset lacks real evidence"),
                        "real",
                    )
                if result.code != ExitCode.COMPLETED:
                    return ProviderResult(
                        result.code,
                        (*completed, name + " reset " + phase + " incomplete", *result.reasons),
                        "real",
                    )
                completed.append(name + " reset " + phase + " completed")
        return ProviderResult(ExitCode.COMPLETED, tuple(completed), "real")
