"""Explicit real composition: PROJECTCTL_ADAPTER_MODULE=projectctl.jaineel.

All required core workload drivers share this composition. Runtime owner hooks
are an explicit optional input, never automatically discovered or made up.
"""

from functools import partial

from benchmarks.composition import build_bindings


def register(registry, *, runtime=None):
    from benchmarks.g3 import register_g3
    from benchmarks.quality_binding import build_quality_bindings
    from infra.analytics import register as register_infrastructure
    from pipelines.catalog.adapter import register as register_catalog
    from projectctl.runtime import CORE, SetupRegistration, load_runtime
    from services.inventory.adapter import register as register_inventory

    runtime = (runtime if runtime is not None else load_runtime()).validate()
    setup = SetupRegistration(registry, runtime.setup_actions)
    register_infrastructure(setup)
    setup.remaining()
    register_catalog(registry)
    register_inventory(registry)
    for workload in sorted(CORE):
        registry.register_workload_factory(
            workload,
            partial(
                build_bindings, workload, registry=registry, owners=runtime.workloads.get(workload)
            ),
        )
    registry.register_workload_factory(
        "W-QUALITY", partial(build_quality_bindings, owners=runtime.quality)
    )
    register_g3(registry, runtime.g3)
    for case_id, binding in runtime.cases.items():
        registry.register_case(case_id, binding)
