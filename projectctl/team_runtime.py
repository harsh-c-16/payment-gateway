"""Lazy team composition; missing owner handoffs remain explicit dependencies.

PROJECTCTL_RUNTIME_MODULE=projectctl.team_runtime supplies M4. Additional
reviewed modules are listed in PROJECTCTL_OWNER_RUNTIME_MODULES (comma-separated).
Every module returns RuntimeBindings; registration never starts a service.
"""

import importlib
import os
import re
from dataclasses import replace

from projectctl.providers import DependencyError
from projectctl.runtime import RuntimeBindings, merge_runtimes
from projectctl.setup import (
    MigrationCoordinator,
    ResetCoordinator,
    migrate_catalog,
    migrate_conversation,
)


def runtime_bindings():
    from infra.analytics import migrate_action
    from infra.analytics_runtime import runtime_bindings as analytics_bindings

    bindings = [analytics_bindings()]
    modules = os.environ.get("PROJECTCTL_OWNER_RUNTIME_MODULES", "")
    for name in filter(None, (part.strip() for part in modules.split(","))):
        if name == __name__ or not re.fullmatch(r"[A-Za-z_]\w*(\.[A-Za-z_]\w*)*", name):
            raise DependencyError("invalid explicit owner runtime module")
        value = importlib.import_module(name).runtime_bindings()
        if not isinstance(value, RuntimeBindings):
            raise DependencyError("owner module must return RuntimeBindings")
        bindings.append(value)
    runtime = merge_runtimes(*bindings)
    performance_review = os.environ.get("PROJECTCTL_PERFORMANCE_REVIEW_PATH")
    if performance_review:
        from projectctl.config import repo_path

        repo_path(performance_review)
        runtime = replace(
            runtime,
            workloads={
                name: replace(callbacks, performance_review_path=performance_review)
                if callbacks.performance_review_path is None
                else callbacks
                for name, callbacks in runtime.workloads.items()
            },
        )
    migrations = {
        "conversation": migrate_conversation,
        "catalog": migrate_catalog,
        "analytics": migrate_action,
    }
    if migrations.keys() & runtime.migrations.keys():
        raise DependencyError("duplicate built-in migration participant")
    migrations.update(runtime.migrations)
    if runtime.setup_actions:
        raise DependencyError(
            "team runtime composes participants; conflicting setup override supplied"
        )
    return RuntimeBindings(
        workloads=runtime.workloads,
        quality=runtime.quality,
        g3=runtime.g3,
        cases=runtime.cases,
        migrations=migrations,
        resets=runtime.resets,
        setup_actions={
            "db migrate": MigrationCoordinator(migrations),
            "env reset": ResetCoordinator(runtime.resets),
        },
    ).validate()
