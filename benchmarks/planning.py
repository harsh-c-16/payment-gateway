"""Recorded paired ordering, controlled matrix expansion and hash-checked reuse."""

import itertools
import json
import random
from dataclasses import dataclass
from uuid import uuid4

from projectctl.artifacts import content_hash, file_hash, git_state
from projectctl.config import ALLOWED_DIFFS, InputError, resolve_config


@dataclass(frozen=True)
class Trial:
    workload: str
    variant: str
    repetition: int
    fault: str
    config: object
    order: dict


def check_pair_controls(left, right):
    """Only registered treatment parameters and their runtime aliases may differ."""
    a, b = left.config.model_dump(), right.config.model_dump()
    allowed = ALLOWED_DIFFS[left.variant] | ALLOWED_DIFFS[right.variant]
    if left.workload != right.workload or left.repetition != right.repetition:
        raise InputError("pair workload/repetition differs")
    if left.fault != right.fault:
        raise InputError("pair fault profiles differ")
    if "retrieval_mode" in allowed:
        a["retrieval"].pop("mode")
        b["retrieval"].pop("mode")
    if "assistant_mode" in allowed:
        for value in (a, b):
            for key in ("mode", "allow_intent_llm", "llm_max_calls"):
                value["assistant"].pop(key)
    if a != b:
        raise InputError("pair changes frozen inputs/resources/quality controls")
    pa = left.config.variants[left.variant].config.model_dump()
    pb = right.config.variants[right.variant].config.model_dump()
    if {key for key in pa if pa[key] != pb[key]} - allowed:
        raise InputError("pair changes unregistered treatment parameters")


def plan_trials(config, workload, variants, repetitions=None, faults=("none",), *, series=None):
    repetitions = repetitions or config.timing.repetitions
    if type(repetitions) is not int or repetitions <= 0 or len(set(variants)) != len(variants):
        raise InputError("positive repetitions and distinct variants required")
    if set(faults) - config.faults.keys():
        raise InputError("unregistered fault profile")
    config = config.model_copy(deep=True)
    config.timing.repetitions = repetitions
    resolved = {variant: resolve_config(config, workload, variant) for variant in variants}
    rng = random.Random(config.generator.seed)
    session_id, trials = str(uuid4()), []
    for fault, rep in itertools.product(faults, range(1, repetitions + 1)):
        children = [
            (v, child)
            for v in variants
            for child in (("unpartitioned", "date_type") if v == "F-PARTITION" else (None,))
        ]
        rng.shuffle(children)
        group = []
        for variant, child in children:
            effective = resolved[variant].variants[variant].config.model_dump()
            if child:
                effective |= {"file_layout": "compact", "partitioning": child}
            config_sha = content_hash(resolved[variant].model_dump())
            controls = {
                "workload": workload,
                "variant": variant,
                "repetition": rep,
                "fault": fault,
                "config_sha256": config_sha,
                "layout_child": child,
                "effective_parameters": effective,
                "series": series or {},
            }
            order = controls | {
                "order_seed": config.generator.seed,
                "session_id": session_id,
                "pair_id": f"{session_id}:{fault}:{rep}",
                "execution_index": len(trials),
                "trial_key": content_hash(controls),
            }
            trial = Trial(workload, variant, rep, fault, resolved[variant], order)
            if group:
                check_pair_controls(group[0], trial)
            group.append(trial)
            trials.append(trial)
    return trials


def plan_matrix(config, matrix):
    trials, pending, seen = [], [], set()
    for row_index, row in enumerate(matrix.rows):
        if row.selection == "measured_best":
            pending.append({"row": row_index, "reason": "C-BEST requires measured selection (P9)"})
            continue
        for mode, keys, rate in itertools.product(
            row.retrieval_modes or [None],
            row.key_distributions or [None],
            row.rates_per_second or [None],
        ):
            controls = config.model_copy(deep=True)
            controls.timing.repetitions = matrix.repetitions
            if mode:
                # This is a paired series control, applied equally to every variant.
                for variant in controls.variants.values():
                    if variant.config.retrieval_mode in {"lexical", "filter_only"}:
                        variant.config.retrieval_mode = mode
                controls.retrieval.mode = mode
            if keys:
                controls.generator.key_distribution = keys
            if rate:
                controls.workloads[row.workload].rate_per_second = float(rate)
            series = {"retrieval_mode": mode, "key_distribution": keys, "rate": rate}
            for trial in plan_trials(
                controls, row.workload, row.variants, matrix.repetitions, row.faults, series=series
            ):
                if trial.order["trial_key"] not in seen:
                    seen.add(trial.order["trial_key"])
                    trials.append(trial)
    return trials, pending


def reusable_run(directory, trial):
    """Fail closed on corruption. INCOMPLETE and stub runs are never reusable."""
    try:
        from projectctl.cli import preflight

        if preflight(trial.config, trial.workload):
            return False
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
        order = json.loads((directory / "execution_order.json").read_text(encoding="utf-8"))
        execution = json.loads((directory / "execution.json").read_text(encoding="utf-8"))
        current_git = git_state().model_dump()
        if (
            manifest["content_sha256"] != content_hash(manifest)
            or manifest["status"] != "MEASURED"
            or manifest["correctness_passed"] is not True
            or summary["test_mode"] != "real"
            or summary["exit_code"] != 0
            or execution["evidence_kind"] != "performance"
            or execution["test_mode"] != "real"
            or execution["sut_performance"] != "MEASURED"
            or order["trial_key"] != trial.order["trial_key"]
            or manifest["resolved_config"] != trial.config.model_dump()
            or current_git["dirty"] is not False
            or manifest["git"] != current_git
        ):
            return False
        for ref in manifest["artifacts"]:
            path = (directory / ref["path"]).resolve()
            if not path.is_relative_to(directory.resolve()) or file_hash(path) != ref["sha256"]:
                return False
        return bool(manifest["artifacts"])
    except (OSError, ValueError, KeyError, TypeError):
        return False
