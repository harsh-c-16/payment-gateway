"""Load, validate and resolve evaluation controls without contacting any provider."""

from copy import deepcopy
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from projectctl.models import EvaluationConfig, MatrixConfig

ROOT = Path(__file__).resolve().parents[1]


class InputError(ValueError):
    """Invalid user input, not a missing provider."""


class UniqueKeyLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        # YAML merges may override inherited fields; repeated explicit fields are errors.
        keys = set()
        for key_node, _ in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                continue
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in keys:
                raise InputError("configuration keys must be unique strings")
            keys.add(key)
        return super().construct_mapping(node, deep=deep)


def repo_path(value: str) -> Path:
    path = Path(value)
    resolved = (ROOT / path).resolve()
    if path.is_absolute() or not resolved.is_relative_to(ROOT):
        raise InputError("paths must remain within the repository and be repository-relative")
    if "://" in value:
        raise InputError("configuration paths cannot be URLs")
    return resolved


def load_yaml(value: str) -> dict:
    try:
        data = yaml.load(repo_path(value).read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    except (OSError, UnicodeError, yaml.YAMLError, RecursionError) as exc:
        raise InputError(f"cannot read YAML input: {value}") from exc
    if not isinstance(data, dict):
        raise InputError("configuration must be an object")
    return data


ALLOWED_DIFFS = {
    "B0": set(),
    "O1": {"sink_batch_max_rows"},
    "O2": {"catalog_optional_btree"},
    "O3": {"sink_batch_max_rows", "catalog_optional_btree"},
    "P10": set(),
    "P30": {"partitions"},
    "P33": {"partitions", "consumers"},
    "F-COMPACT": {"file_layout"},
    "F-PARTITION": {"file_layout"},
    "I0": set(),
    "I1": {"catalog_load_mode"},
    "R-EXACT": {"retrieval_mode"},
    "R-ANN": {"retrieval_mode"},
    "A-FIXED": set(),
    "A-ASSIST": {"assistant_mode"},
}
WORKLOADS = {
    "W-IMPORT",
    "W-PIPE",
    "W-QUALITY",
    "W-SEARCH",
    "W-CHECKOUT",
    "W-INTEGRATED",
    "W-ANALYTICS",
    "W-AGENT",
}


def validate_config(data: dict) -> EvaluationConfig:
    errors = list(Draft202012Validator(EvaluationConfig.model_json_schema()).iter_errors(data))
    if errors:
        fields = [".".join(map(str, error.absolute_path)) for error in errors]
        raise InputError("invalid configuration fields: " + ", ".join(fields))
    try:
        config = EvaluationConfig.model_validate(data)
    except ValidationError as exc:
        # Do not echo input values, URLs, tokens or Pydantic's raw input repr.
        fields = [".".join(map(str, error["loc"])) for error in exc.errors()]
        raise InputError("invalid configuration fields: " + ", ".join(fields)) from exc
    if set(config.workloads) != WORKLOADS or set(config.variants) != set(ALLOWED_DIFFS):
        raise InputError("all registered workloads and variants must be defined")
    baseline = config.variants["B0"].config.model_dump()
    fixed = {
        "partitions": 1,
        "consumers": 1,
        "sink_batch_max_rows": 1,
        "sink_batch_max_wait_ms": 50,
        "raw_capture_max_bytes": 1048576,
        "raw_capture_max_wait_ms": 50,
        "gold_publish_interval_ms": 250,
        "outbox_poll_ms": 25,
        "outbox_pass_limit": 100,
        "expiry_sweep_ms": 250,
        "catalog_optional_btree": False,
        "catalog_load_mode": "row",
        "catalog_chunk_rows": 1000,
        "file_layout": "small",
        "assistant_mode": "fixed",
    }
    if any(baseline[key] != value for key, value in fixed.items()):
        raise InputError("B0 changes a frozen correctness, batching or durability control")
    for name, variant in config.variants.items():
        if set(variant.allowed_differences) != ALLOWED_DIFFS[name]:
            raise InputError(f"{name}: allowed differences differ from the registered contract")
        actual = {key for key, val in variant.config.model_dump().items() if val != baseline[key]}
        if actual != ALLOWED_DIFFS[name]:
            raise InputError(f"{name}: configuration differs outside its declared experiment")
    expected_changes = {
        "O1": {"sink_batch_max_rows": 100},
        "O2": {"catalog_optional_btree": True},
        "O3": {"sink_batch_max_rows": 100, "catalog_optional_btree": True},
        "P30": {"partitions": 3},
        "P33": {"partitions": 3, "consumers": 3},
        "I1": {"catalog_load_mode": "copy"},
        "F-COMPACT": {"file_layout": "compact"},
        "F-PARTITION": {"file_layout": "partition_comparison"},
        "R-EXACT": {"retrieval_mode": "hybrid_exact"},
        "R-ANN": {"retrieval_mode": "hybrid_ann"},
        "A-ASSIST": {"assistant_mode": "assist"},
    }
    for name, changes in expected_changes.items():
        if any(getattr(config.variants[name].config, key) != val for key, val in changes.items()):
            raise InputError(f"{name}: registered variant values are incorrect")
    profile = config.profile
    if set(profile.services) != set(profile.service_allocations):
        raise InputError("profile requires an allocation for every declared service")
    if sum(a.cpu_cores for a in profile.service_allocations.values()) > profile.sut.cpu_cores:
        raise InputError("service CPU allocations exceed the SUT budget")
    if sum(a.memory_mib for a in profile.service_allocations.values()) > profile.sut.memory_mib:
        raise InputError("service memory allocations exceed the SUT budget")
    for path in (
        config.dataset.source_path,
        config.dataset.dictionary_path,
        config.dataset.canonical_manifest,
        config.dataset.sku_manifest,
        config.artifacts.root,
        config.locks.application.path,
        config.locks.infrastructure.path,
        config.locks.event_schemas.path,
    ):
        if path is not None:
            repo_path(path)
    for name, workload in config.workloads.items():
        if workload.kind == "sustained" and workload.rate_per_second is None:
            raise InputError(f"{name}: sustained workload requires an offered rate")
        if workload.kind == "finite" and workload.record_count is None:
            raise InputError(f"{name}: finite workload requires a record count")
        if workload.kind == "queries" and (
            workload.query_count is None
            or workload.warmups_per_query is None
            or workload.executions_per_query is None
        ):
            raise InputError(
                f"{name}: query workload requires warmups and measured execution counts"
            )
    kinds = {
        "W-IMPORT": "finite",
        "W-QUALITY": "finite",
        "W-AGENT": "finite",
        "W-ANALYTICS": "queries",
    }
    if any(item.kind != kinds.get(name, "sustained") for name, item in config.workloads.items()):
        raise InputError("workload timing kind differs from the runbook")
    if config.workloads["W-AGENT"].required:
        raise InputError("live assistant evaluation is optional")
    if any(not item.required for name, item in config.workloads.items() if name != "W-AGENT"):
        raise InputError("required core workloads cannot be disabled")
    if "none" not in config.faults or config.faults["none"].trigger != "none":
        raise InputError("fault registry requires the none profile")
    return config


def load_config(path="configs/evaluation.yaml") -> EvaluationConfig:
    return validate_config(load_yaml(path))


def load_matrix(path: str, config: EvaluationConfig) -> MatrixConfig:
    try:
        matrix = MatrixConfig.model_validate(load_yaml(path))
    except ValidationError as exc:
        raise InputError("invalid matrix fields") from exc
    for row in matrix.rows:
        for variant in row.variants:
            if row.workload not in config.variants[variant].workloads:
                raise InputError(f"{variant} does not support {row.workload}")
        if set(row.faults) - config.faults.keys():
            raise InputError("matrix contains an unregistered fault")
        if row.retrieval_modes and row.workload != "W-SEARCH":
            raise InputError("retrieval mode series require W-SEARCH")
        if (row.key_distributions or row.rates_per_second) and row.workload != "W-PIPE":
            raise InputError("partition/rate series require W-PIPE")
    return matrix


def resolve_config(config: EvaluationConfig, workload: str, variant: str) -> EvaluationConfig:
    if workload not in config.variants[variant].workloads:
        raise InputError(f"{variant} does not support {workload}")
    data = deepcopy(config.model_dump())
    parameters = config.variants[variant].config
    data["retrieval"]["mode"] = parameters.retrieval_mode
    data["assistant"]["mode"] = parameters.assistant_mode
    enabled = parameters.assistant_mode == "assist"
    data["assistant"]["allow_intent_llm"] = enabled
    data["assistant"]["llm_max_calls"] = int(enabled)
    rate = config.workloads[workload].rate_per_second
    if rate is not None:
        data["generator"]["rate_per_second"] = rate
    return validate_config(data)


def workload_timing(config: EvaluationConfig, workload: str) -> dict:
    """Finite jobs never inherit a fabricated 600-second measurement denominator."""
    item = config.workloads[workload]
    if item.kind == "sustained":
        return config.timing.model_dump()
    return {
        "kind": item.kind,
        "warmup_seconds": None,
        "duration_seconds": None,
        "drain_seconds": config.timing.drain_seconds,
        "repetitions": config.timing.repetitions,
        "warmups_per_query": item.warmups_per_query,
        "executions_per_query": item.executions_per_query,
    }
