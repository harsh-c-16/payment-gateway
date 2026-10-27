"""The runbook command surface and adapter dispatch, without provider business logic."""

import argparse
import re
import sys
from uuid import uuid4

from projectctl.artifacts import canonical_json, file_hash, save_evidence
from projectctl.config import (
    ALLOWED_DIFFS,
    WORKLOADS,
    InputError,
    load_config,
    repo_path,
    resolve_config,
)
from projectctl.models import ExitCode
from projectctl.providers import (
    OWNERS,
    Invocation,
    ProviderRegistry,
    ProviderResult,
    default_registry,
)

SUITES = {
    "contracts",
    "data",
    "smoke",
    "correctness",
    *[f"T-{i:02}" for i in range(1, 13)],
    *[f"D-{i:02}" for i in range(1, 6)],
}


class Parser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **(kwargs | {"allow_abbrev": False}))

    def error(self, message):
        # argparse's message contains caller-supplied values; retain only a safe error kind.
        raise InputError("invalid CLI arguments; use the command's --help")


def positive(value):
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return parsed


def seed(value):
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a nonnegative integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("expected a nonnegative integer")
    return parsed


def csv_values(value):
    values = value.split(",")
    if any(not item or item != item.strip() for item in values) or len(values) != len(set(values)):
        raise argparse.ArgumentTypeError("expected distinct comma-separated names")
    return values


def parser():
    root = Parser(prog="python -m projectctl", description=__doc__)
    groups = root.add_subparsers(dest="group", required=True)
    actions = {}
    for action, owner in OWNERS.items():
        group, command = action.split()
        if group not in actions:
            group_parser = groups.add_parser(group, help=f"{group} actions")
            actions[group] = group_parser.add_subparsers(dest="command", required=True)
        sub = actions[group].add_parser(command, help=f"{action}; provider: {owner}")
        sub.set_defaults(action=action)
        if action in {"env up", "env verify"}:
            sub.add_argument("--profile", required=True)
        if action in {
            "env reset",
            "db migrate",
            "catalog import",
            "catalog verify",
            "inventory seed",
            "projection wait",
        }:
            sub.add_argument("--namespace", required=True)
        if action == "contracts check":
            sub.add_argument("--all", action="store_true", required=True)
        if action in {"catalog profile", "catalog import"}:
            sub.add_argument("--source", required=True)
            sub.add_argument("--rules", choices=["flipkart-v1"], required=True)
            sub.add_argument("--out", required=True)
        if action == "catalog import":
            sub.add_argument("--load-mode", choices=["row", "copy"], required=True)
        if action == "catalog verify":
            sub.add_argument("--manifest", required=True)
        if action in {"inventory seed", "projection wait"}:
            sub.add_argument("--sku-manifest", required=True)
        if action == "inventory seed":
            sub.add_argument("--profile", required=True)
            sub.add_argument("--seed", type=seed, required=True)
        if action == "projection wait":
            sub.add_argument("--timeout-seconds", type=positive, required=True)
        if action in {"fixtures build", "eval run", "benchmark run", "benchmark matrix"}:
            sub.add_argument("--config", required=True)
        if action in {"benchmark run", "benchmark matrix"}:
            sub.add_argument(
                "--readiness", help="P9 owner-reviewed real correctness/resource receipt"
            )
        if action == "benchmark run":
            sub.add_argument(
                "--smoke", action="store_true", help="5-second B0 setup check; never performance"
            )
        if action == "benchmark matrix":
            sub.add_argument("--selection", help="reviewed measured C-BEST choice receipt")
        if action == "fixtures build":
            sub.add_argument("--seed", type=seed, required=True)
        if action == "eval run":
            sub.add_argument("--suite", type=csv_values, required=True)
        if action == "benchmark run":
            sub.add_argument("--workload", choices=sorted(WORKLOADS), required=True)
            sub.add_argument("--variants", type=csv_values, required=True)
            sub.add_argument("--repetitions", type=positive)
            sub.add_argument("--faults", type=csv_values, default=["none"])
        if action == "benchmark matrix":
            sub.add_argument("--matrix", required=True)
        if action == "benchmark compare":
            sub.add_argument(
                "--baseline",
                type=csv_values,
                required=True,
                help="three comma-separated run directories",
            )
            sub.add_argument(
                "--candidate",
                type=csv_values,
                required=True,
                help="three comma-separated run directories",
            )
            sub.add_argument("--out", required=True)
        if action == "benchmark reconcile":
            sub.add_argument("--run-dir", required=True)
        if action == "report build":
            sub.add_argument("--matrix-results", required=True)
            sub.add_argument("--out", required=True)
    return root


def validate_arguments(args):
    for key in (
        "config",
        "source",
        "out",
        "manifest",
        "sku_manifest",
        "matrix",
        "baseline",
        "candidate",
        "run_dir",
        "matrix_results",
        "readiness",
        "selection",
    ):
        if args.get(key) is not None:
            for value in args[key] if isinstance(args[key], list) else [args[key]]:
                repo_path(value)
    if "namespace" in args:
        namespace = args["namespace"]
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,61}", namespace):
            raise InputError("invalid namespace")
        if args["action"] == "env reset" and (
            not re.fullmatch(r"bench-[a-z0-9][a-z0-9-]*", namespace)
            or re.match(r"bench-(dev|live|prod|production)(-|$)", namespace)
        ):
            raise InputError("reset requires an isolated bench namespace; dev/live are protected")
    if "profile" in args and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", args["profile"]):
        raise InputError("invalid profile name")
    if "variants" in args and set(args["variants"]) - ALLOWED_DIFFS.keys():
        raise InputError(
            "unregistered variant; C-BEST requires measured selection in a later milestone"
        )
    if "suite" in args and set(args["suite"]) - SUITES:
        raise InputError("unregistered test suite or case")


def preflight(config, workload=None):
    """Missing evidence blocks real execution; these checks never declare a provider ready."""
    reasons = []
    if config.state != "ready":
        reasons.append("configuration is explicitly draft")
    if config.profile.allocation_status != "enforced":
        reasons.append("resource profile has not been enforced/verified by infrastructure")
    for name in ("application", "infrastructure", "event_schemas"):
        lock = getattr(config.locks, name)
        if lock.path is None or lock.sha256 is None:
            reasons.append(f"{name} lock path/hash unavailable")
        elif not repo_path(lock.path).is_file():
            reasons.append(f"{name} lock file unavailable")
        elif file_hash(repo_path(lock.path)) != lock.sha256:
            raise InputError(f"{name} lock SHA-256 differs from the frozen configuration")
    dataset = config.dataset
    for name in (
        "expected_sha256",
        "dictionary_path",
        "dictionary_sha256",
        "canonical_manifest",
        "sku_manifest",
    ):
        if getattr(dataset, name) is None:
            reasons.append(f"dataset.{name} unavailable")
    source = repo_path(dataset.source_path)
    if not source.is_file():
        reasons.append("source CSV unavailable; exact-file data gates NOT_RUN")
    elif dataset.expected_sha256 is not None and file_hash(source) != dataset.expected_sha256:
        raise InputError("source CSV SHA-256 differs from the frozen dataset")
    for name in ("dictionary_path", "canonical_manifest", "sku_manifest"):
        path = getattr(dataset, name)
        if path and not repo_path(path).is_file():
            reasons.append(f"dataset.{name} file unavailable")
    if (
        dataset.dictionary_path
        and dataset.dictionary_sha256
        and repo_path(dataset.dictionary_path).is_file()
        and file_hash(repo_path(dataset.dictionary_path)) != dataset.dictionary_sha256
    ):
        raise InputError("dictionary SHA-256 differs from the frozen dataset")
    if config.generator.template_sha256 is None:
        reasons.append("generator logical fixture hash unavailable")
    if workload and config.workloads[workload].template_sha256 is None:
        reasons.append(f"{workload} template hash unavailable")
    if workload in {"W-SEARCH", "W-INTEGRATED", "W-AGENT"}:
        for name in ("query_sha256", "label_sha256"):
            if getattr(config.retrieval, name) is None:
                reasons.append(f"retrieval.{name} unavailable")
    if config.retrieval.mode.startswith("hybrid"):
        for name in ("embedding_sha256", "model_sha256"):
            if getattr(config.retrieval, name) is None:
                reasons.append(f"retrieval.{name} unavailable")
    if config.assistant.allow_intent_llm:
        if not all(
            (config.assistant.provider, config.assistant.model, config.assistant.prompt_sha256)
        ):
            reasons.append(
                "optional live intent provider/model/prompt not configured; live NOT_RUN"
            )
    return reasons


def execute(args, registry: ProviderRegistry):
    config = load_config(args["config"]) if "config" in args else None
    if config and "seed" in args:
        config.generator.seed = args["seed"]
    if config and "faults" in args and set(args["faults"]) - config.faults.keys():
        raise InputError("unregistered fault profile")
    if args["action"] in {"benchmark run", "benchmark matrix"}:
        from projectctl.benchmark_adapter import execute_benchmarks

        return execute_benchmarks(args, registry, config)
    if args["action"] == "benchmark compare":
        from benchmarks.comparison import execute_comparison

        invocation = Invocation(
            args["action"], args.copy(), None, str(uuid4()), "bench-" + uuid4().hex
        )
        return [execute_comparison(invocation)]
    if args["action"] in {"eval run", "benchmark reconcile"}:
        from benchmarks.integration import execute_evaluation, execute_reconciliation

        invocation = Invocation(
            args["action"], args.copy(), config, str(uuid4()), "bench-" + uuid4().hex
        )
        output = (
            execute_evaluation(invocation, registry)
            if args["action"] == "eval run"
            else execute_reconciliation(invocation)
        )
        return [output]
    planned = [(None, None, None)]
    outputs = []
    for workload, variant, repetition in planned:
        resolved = resolve_config(config, workload, variant) if workload else config
        run_id = str(uuid4())
        namespace = args.get("namespace", "bench-" + run_id)
        invocation = Invocation(args["action"], args.copy(), resolved, run_id, namespace)
        reasons = []
        if registry.binding_failure:
            reasons.append(registry.binding_failure)
        if resolved and args["action"] in {"eval run", "benchmark run", "benchmark matrix"}:
            reasons.extend(preflight(resolved, workload))
        missing = registry.missing(args["action"])
        if missing:
            reasons.append(missing)
        if reasons:
            result = ProviderResult(ExitCode.DEPENDENCY_FAILURE, tuple(reasons), "offline")
        else:
            try:
                result = registry.invoke(invocation)
            except Exception as exc:
                # An adapter is an external boundary. Preserve evidence even when it
                # violates its exception contract; never copy potentially secret text.
                result = ProviderResult(
                    ExitCode.DEPENDENCY_FAILURE,
                    (f"provider unavailable or failed: {type(exc).__name__}; no fallback used",),
                    "real",
                )
        outputs.append(
            save_evidence(
                invocation, result, workload=workload, variant=variant, repetition=repetition
            )
        )
    return outputs


def main(argv=None, *, registry=None):
    try:
        args = vars(parser().parse_args(argv))
        validate_arguments(args)
        outputs = execute(args, registry if registry is not None else default_registry())
        code = max(item["exit_code"] for item in outputs)
        payload = outputs[0] if len(outputs) == 1 else {"exit_code": code, "runs": outputs}
    except InputError as exc:
        invocation = Invocation("invalid input", {}, None, str(uuid4()), "bench-invalid-input")
        result = ProviderResult(ExitCode.BAD_INPUT, (str(exc),), "offline")
        try:
            payload = save_evidence(invocation, result)
            code = int(ExitCode.BAD_INPUT)
        except OSError:
            payload = {
                "exit_code": 4,
                "status": "INCOMPLETE",
                "test_mode": "offline",
                "reasons": ["evidence storage unavailable for invalid input"],
            }
            code = int(ExitCode.DEPENDENCY_FAILURE)
    except OSError:
        # Evidence storage failure is incomplete evidence, never successful startup.
        payload = {
            "exit_code": 4,
            "status": "INCOMPLETE",
            "test_mode": "offline",
            "reasons": ["evidence storage unavailable"],
        }
        code = int(ExitCode.DEPENDENCY_FAILURE)
    sys.stdout.write(canonical_json(payload).decode("utf-8") + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
