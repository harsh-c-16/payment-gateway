"""Prepare/verify an exact-input handoff. Never start services or run evaluations.

python -m projectctl.evaluation_packet --out artifacts/evaluation-handoff/NAME
python -m projectctl.evaluation_packet --verify artifacts/evaluation-handoff/NAME
"""

import argparse
import json
from collections import defaultdict

import yaml

from benchmarks.composition import catalog_projection
from benchmarks.integration_cases import CASES
from benchmarks.workloads import generate_workload
from projectctl.artifacts import content_hash, file_hash, git_state, write_json
from projectctl.config import ROOT, load_config, repo_path, validate_config
from projectctl.input_pins import PUBLISHED, review_input_pins, text_pin
from projectctl.provider_validation import SURFACES, inspect_surface, references

REVISION = "data/catalog/flipkart-v1-3a401f32ca99379f8298ce42/"
AUDIT_PATHS = (
    "benchmarks/analytics_recheck.py",
    "benchmarks/performance.py",
    "benchmarks/quality_binding.py",
    "benchmarks/quality_sources.py",
    "benchmarks/quality_audit.py",
    "benchmarks/quality_publisher.py",
    "benchmarks/quality.py",
    "benchmarks/workloads.py",
    "benchmarks/quality_trial.py",
    "benchmarks/seed_audit.py",
    "projectctl/team_runtime.py",
    "benchmarks/pipeline_audit.py",
    "benchmarks/reconciliation.py",
    "pipelines/ingestion/quality.py",
    "pipelines/storage/readers.py",
    "pipelines/curation/sink_observations.py",
    "pipelines/storage/publication.py",
    "pipelines/ingestion/bronze.py",
    "shared/event_transport/codec.py",
    "shared/event_transport/schemas.py",
    "shared/event_transport/consumer.py",
    "infra/analytics_runtime.py",
    "infra/analytics_resources.py",
    "infra/audit_roles.py",
    "pipelines/ingestion/adapters.py",
    "infra/analytics_deployment.py",
)


def process_profile(document, name):
    plan = document["profiles"][name]
    processes = list(plan["processes"])
    if plan.get("extends"):
        processes = process_profile(document, plan["extends"])[1] + processes
    if len({p["name"] for p in processes}) != len(processes):
        raise ValueError("duplicate process allocation")
    totals = defaultdict(lambda: {"cpu_cores": 0.0, "memory_mib": 0})
    pools = defaultdict(int)
    for process in processes:
        if process["cpu_cores"] <= 0 or process["memory_mib"] <= 0:
            raise ValueError("positive process limits required")
        allocation = totals[process["service"]]
        for field in ("cpu_cores", "memory_mib"):
            allocation[field] += process[field]
        if "connections" in process:
            if type(process["connections"]) is not int or process["connections"] <= 0:
                raise ValueError("positive integer process connection cap required")
            pools[process["service"]] += process["connections"]
    if (
        sum(p["cpu_cores"] for p in processes) > plan["sut"]["cpu_cores"]
        or sum(p["memory_mib"] for p in processes) > plan["sut"]["memory_mib"]
    ):
        raise ValueError("processes exceed SUT budget")
    analytics = totals["analytics"]
    group = document["consumer_group_total"]
    if analytics != {
        "cpu_cores": group["cpu_cores"] + 0.5,
        "memory_mib": group["memory_mib"] + 384,
    }:
        raise ValueError("analytics budget must include API plus fixed worker-group total")
    return {
        "name": name,
        "allocation_status": "planned",
        "sut": plan["sut"],
        "generator": document["generator"],
        "services": sorted(totals),
        "service_allocations": dict(totals),
        "connection_pools": dict(pools),
        "consumer_group_total": group,
    }, processes


def worker_processes(processes, consumers):
    """Expose each actual consumer; only worker zero owns publisher/relay threads."""
    expanded = []
    if type(consumers) is not int or consumers not in {1, 3}:
        raise ValueError("one or three analytics consumers required")
    for process in processes:
        if process["name"] != "analytics-consumer-group":
            expanded.append(process)
            continue
        cpu = round(process["cpu_cores"] * 1_000_000_000)
        if process.get("connections") != 14:
            raise ValueError("analytics group requires twelve sink plus two publisher/relay slots")
        for index in range(consumers):
            expanded.append(
                process
                | {
                    "name": f"analytics-worker-{index}",
                    "cpu_cores": (cpu // consumers + (index < cpu % consumers)) / 1_000_000_000,
                    "memory_mib": process["memory_mib"] // consumers
                    + (index < process["memory_mib"] % consumers),
                    "connections": 12 // consumers + (2 if index == 0 else 0),
                    "roles": ["consumer", "Gold publisher", "analytics outbox relay"]
                    if index == 0
                    else ["consumer"],
                }
            )
    return expanded


def prepare(out, *, config_path="configs/evaluation.yaml"):
    config = load_config(config_path)
    if file_hash(repo_path(config.dataset.source_path)) != config.dataset.expected_sha256:
        raise ValueError("source bytes differ from the canonical file 08 checksum")
    config.dataset.dictionary_path = PUBLISHED["dictionary"][0]
    config.dataset.dictionary_sha256 = file_hash(repo_path(config.dataset.dictionary_path))
    config.dataset.canonical_manifest = REVISION + "normalized_manifest.json"
    config.dataset.sku_manifest = REVISION + "sku_manifest.json"
    config.retrieval.query_sha256 = file_hash(repo_path(PUBLISHED["queries"][0]))
    # Rule-derived relevance scores are diagnostic; they are not human judgements.
    config.retrieval.label_sha256 = None
    for name, path in (
        ("application", "uv.lock"),
        ("infrastructure", "infra/images.lock.json"),
        ("event_schemas", "contracts/events/manifest.json"),
    ):
        lock = getattr(config.locks, name)
        lock.path, lock.sha256 = path, file_hash(repo_path(path))
    projection = catalog_projection(config)
    normalized = json.loads(repo_path(config.dataset.canonical_manifest).read_text("utf-8"))
    if (
        text_pin(repo_path(config.dataset.dictionary_path))["lf_text_sha256"]
        != normalized["dictionary_sha256"]
    ):
        raise ValueError("dictionary identity differs from Harsh's normalized manifest")
    input_paths = {
        config_path,
        "configs/core_matrix.yaml",
        "configs/evaluation_profiles.json",
        "uv.lock",
        "infra/images.lock.json",
        "contracts/events/manifest.json",
        config.dataset.source_path,
        config.dataset.dictionary_path,
        config.dataset.canonical_manifest,
        config.dataset.sku_manifest,
        PUBLISHED["queries"][0],
        *AUDIT_PATHS,
        "projectctl/evaluation_packet.py",
        "projectctl/provider_validation.py",
        "projectctl/contract_checks.py",
        "projectctl/team_runtime.py",
        "projectctl/runtime.py",
        "projectctl/setup.py",
    }
    input_paths.update(
        p.relative_to(ROOT).as_posix() for p in (ROOT / "contracts/fixtures").rglob("*.json")
    )
    for surface in SURFACES:
        input_paths.update(ref["path"] for ref in references(ROOT, surface))
    pins = [{"path": p, "sha256": file_hash(repo_path(p))} for p in sorted(input_paths)]
    config.generator.template_sha256 = content_hash({"inputs": pins})
    templates = {
        "W-IMPORT": (),
        "W-PIPE": (),
        "W-QUALITY": (),
        "W-SEARCH": json.loads(repo_path(PUBLISHED["queries"][0]).read_text("utf-8"))["queries"],
        "W-ANALYTICS": [{"query_id": f"Q{i}"} for i in range(1, 7)],
    }
    recipes = {}
    for workload, rows in templates.items():
        item = config.workloads[workload]
        recipe = generate_workload(
            workload,
            config.generator.seed,
            projection,
            rate_per_second=item.rate_per_second,
            duration_seconds=config.timing.duration_seconds,
            warmup_seconds=config.timing.warmup_seconds,
            key_count=config.generator.key_count,
            key_distribution=config.generator.key_distribution,
            templates=rows,
            record_count=item.record_count,
            warmups_per_query=item.warmups_per_query or 0,
            executions_per_query=item.executions_per_query or 1,
        ).as_dict()
        recipes[workload] = recipe
        item.template_sha256 = recipe["logical_fixture_sha256"]
    plans = json.loads(repo_path("configs/evaluation_profiles.json").read_text("utf-8"))
    out.mkdir(parents=True, exist_ok=False)
    write_json(
        out / "generator_inputs.json",
        {
            "inputs": pins,
            "content_sha256": config.generator.template_sha256,
        },
    )
    for workload, recipe in recipes.items():
        write_json(out / (workload + ".recipe.json"), recipe)
    profile_details = {}
    for name in plans["profiles"]:
        profile, processes = process_profile(plans, name)
        candidate = config.model_copy(deep=True)
        candidate.profile = type(config.profile).model_validate(profile)
        candidate.state = "draft"
        allowed = set(plans["profiles"][name]["workloads"])
        for variant in candidate.variants.values():
            variant.workloads = [workload for workload in variant.workloads if workload in allowed]
        validate_config(candidate.model_dump())
        target = out / (name + ".yaml")
        with target.open("x", encoding="utf-8", newline="\n") as stream:
            yaml.safe_dump(candidate.model_dump(), stream, sort_keys=False)
        profile_details[name] = {
            "config": target.relative_to(ROOT).as_posix(),
            "sha256": file_hash(target),
            "processes": worker_processes(processes, 1),
            "processes_p33": worker_processes(processes, 3),
            "allowed_workloads": plans["profiles"][name]["workloads"],
            "enforcement": "NOT_RUN",
            "machine": None,
        }
    write_json(out / "recipes.json", recipes)
    write_json(out / "input_hash_policy.json", review_input_pins())
    write_json(
        out / "provider_review.proposed.json",
        {
            "schema_version": 1,
            "status": "REVIEW_REQUIRED",
            "surfaces": {
                surface: {
                    "status": "REVIEW_REQUIRED",
                    "reviewers": [],
                    "contracts": references(ROOT, surface),
                }
                for surface in SURFACES
            },
        },
    )
    write_json(
        out / "analytics_review.proposed.json",
        {
            "schema_version": 1,
            "status": "REVIEW_REQUIRED",
            "reviewers": [],
            "read_only_audit": True,
            "namespace_scoped": True,
            "contracts": [{"path": p, "sha256": file_hash(repo_path(p))} for p in AUDIT_PATHS],
        },
    )
    from projectctl.team_runtime import runtime_bindings

    runtime = runtime_bindings()
    write_json(
        out / "integration_inventory.json",
        {
            "runtime": "projectctl.team_runtime",
            "runtime_readiness": "NOT_RUN",
            "migrations_registered": sorted(runtime.migrations),
            "resets_registered": sorted(runtime.resets),
            "cases": [
                {
                    "case_id": c.case_id,
                    "owner": c.owner,
                    "binding_registered": c.case_id in runtime.cases or c.case_id in runtime.g3,
                    "status": "NOT_RUN",
                }
                for c in CASES
            ],
            "quality_trial": (
                "benchmarks.quality_trial.run_g1; separate G1 runner, not smoke/G1 CaseBinding"
            ),
        },
    )
    write_json(out / "provider_validation.json", [inspect_surface(ROOT, s) for s in SURFACES])
    snapshot = {
        "schema_version": 1,
        "status": "INPUTS_PINNED_REVIEW_PENDING",
        "git": git_state().model_dump(),
        "source_sha256": file_hash(repo_path(config.dataset.source_path)),
        "dataset_revision": projection["dataset_revision"],
        "profiles": profile_details,
        "inputs": pins,
        "evaluation": "NOT_RUN",
        "performance": None,
        "pending_inputs": [
            "execution machine and enforced resource receipt",
            "affected-owner mapping reviews",
            "operational runtime/case bindings",
            "W-CHECKOUT/W-INTEGRATED reviewed templates",
            "human relevance labels",
        ],
        "packet_files": [
            {"path": p.relative_to(ROOT).as_posix(), "sha256": file_hash(p)}
            for p in sorted(out.iterdir())
            if p.is_file()
        ],
    }
    snapshot["content_sha256"] = content_hash(snapshot)
    write_json(out / "input_lock.json", snapshot)
    return snapshot


def verify(directory):
    snapshot = json.loads((directory / "input_lock.json").read_text("utf-8"))
    if snapshot["content_sha256"] != content_hash(snapshot):
        raise ValueError("input lock changed")
    for ref in snapshot["inputs"] + snapshot["packet_files"]:
        if file_hash(repo_path(ref["path"])) != ref["sha256"]:
            raise ValueError("frozen bytes changed: " + ref["path"])
    return snapshot


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--out")
    choice.add_argument("--verify")
    args = parser.parse_args(argv)
    try:
        result = prepare(repo_path(args.out)) if args.out else verify(repo_path(args.verify))
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "INCOMPLETE",
                    "error": type(exc).__name__,
                    "reason": "packet input/storage/runtime dependency failed",
                    "evaluation": "NOT_RUN",
                }
            )
        )
        return 4
    print(
        json.dumps(
            {
                "status": result["status"],
                "content_sha256": result["content_sha256"],
                "evaluation": "NOT_RUN",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
