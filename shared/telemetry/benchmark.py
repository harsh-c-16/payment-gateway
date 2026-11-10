"""Opt-in benchmark identity headers; carries identity, never a requested outcome."""

import os
import re

SCENARIO_HEADER = "X-Benchmark-Scenario-ID"
SEED_HEADER = "X-Benchmark-Seed"


def benchmark_headers(headers, namespace):
    """Validate at every ingress, including internal participant calls.

    Version 2 IDs encode phase, logical ordinal and template ID. An empty mapping
    leaves ordinary clients on the simulator's normal path. Flags fail closed.
    """
    lowered = {key.lower(): value for key, value in headers.items()}
    scenario = lowered.get(SCENARIO_HEADER.lower())
    seed = lowered.get(SEED_HEADER.lower())
    if scenario is None and seed is None:
        return {}
    if (
        os.environ.get("BENCHMARK_MODE", "false").lower() != "true"
        or os.environ.get("FAULT_INJECTION_ENABLED", "false").lower() != "true"
        or not re.fullmatch(r"bench-[a-z0-9][a-z0-9-]{0,55}", namespace)
        or re.match(r"bench-(dev|live|prod|production)(-|$)", namespace)
    ):
        raise PermissionError("Benchmark identity requires both flags and an isolated namespace.")
    if (
        not isinstance(scenario, str)
        or len(scenario) > 128
        or not re.fullmatch(r"(warmup|measurement):[0-9]{6,12}:[A-Za-z0-9_.:-]+", scenario)
        or not isinstance(seed, str)
        or not re.fullmatch(r"[0-9]{1,19}", seed)
        or int(seed) > 2**63 - 1
    ):
        raise ValueError(
            "Paired version-2 benchmark scenario ID and nonnegative int64 seed required."
        )
    return {SCENARIO_HEADER: scenario, SEED_HEADER: str(int(seed))}
