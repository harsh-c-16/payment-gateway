"""Global migration coordination delegates to each owner's explicit participant."""

import os

from projectctl.models import ExitCode
from projectctl.providers import ProviderResult

DATABASE_OWNERS = ("conversation", "catalog", "orders", "inventory", "payments", "analytics")


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
