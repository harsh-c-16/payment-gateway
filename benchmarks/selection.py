"""Review a measured C-BEST choice; never manufacture an optimization implementation."""

from benchmarks.comparison import compare_runs
from benchmarks.performance import checked_ref, controls_hash, read_json
from projectctl.artifacts import content_hash, git_state
from projectctl.config import repo_path
from projectctl.models import EvaluationConfig
from projectctl.providers import DependencyError


def load_selection(path, config):
    if path is None:
        return None
    receipt = read_json(repo_path(path))
    if (
        set(receipt) != {"schema_version", "choices", "content_sha256"}
        or receipt["schema_version"] != 1
        or receipt["content_sha256"] != content_hash(receipt)
        or set(receipt["choices"]) != {"W-PIPE", "W-INTEGRATED"}
    ):
        raise DependencyError("invalid measured C-BEST selection receipt")
    choices = {}
    current_git = git_state().model_dump()
    for workload, choice in receipt["choices"].items():
        if (
            set(choice)
            != {"variant", "comparisons", "metric", "rationale", "reviewers", "costs_accepted"}
            or not choice["rationale"].strip()
            or choice["costs_accepted"] is not True
            or set(choice["reviewers"]) != {"Jaineel", "Harsh", "Aditya", "Vichitr"}
            or choice["variant"] not in config.variants
            or workload not in config.variants[choice["variant"]].workloads
            or not choice["comparisons"]
        ):
            raise DependencyError("reviewed supported candidate/cost rationale required")
        reports = []
        for ref in choice["comparisons"]:
            report = read_json(checked_ref(ref))
            if (
                report.get("content_sha256") != content_hash(report)
                or len(report.get("runs", [])) != 6
                or report.get("status") != "MEASURED"
            ):
                raise DependencyError("measured comparison receipt changed or incomplete")
            # Recompute from all six raw bundles, not from a winner flag in JSON.
            paths = [
                str(checked_ref(r).parent.relative_to(repo_path("."))).replace("\\", "/")
                for r in report["runs"]
            ]
            for ref in report["runs"]:
                manifest = read_json(checked_ref(ref))
                try:
                    same_study = controls_hash(
                        EvaluationConfig.model_validate(manifest["resolved_config"])
                    ) == controls_hash(config)
                except (ValueError, KeyError, TypeError) as exc:
                    raise DependencyError("selection study identity unavailable") from exc
                if manifest.get("git") != current_git or not same_study:
                    raise DependencyError(
                        "selected comparison belongs to a different study or revision"
                    )
            if compare_runs(paths[:3], paths[3:]) != report:
                raise DependencyError("selection comparison differs from raw evidence")
            reports.append(report)
        candidate = choice["variant"]
        supporting = [
            r
            for r in reports
            if r["workload"] == workload
            and (candidate == "B0" or r["candidate_variant"] == candidate)
        ]
        if not supporting:
            raise DependencyError("selected workload has no measured candidate interaction trial")
        metrics = [m for r in supporting for m in r["metrics"] if m["name"] == choice["metric"]]
        if not metrics or any(m["status"] != "MEASURED" for m in metrics):
            raise DependencyError("selection metric lacks three measured repetitions")
        if candidate != "B0" and not any(
            m["improvement_percent"] is not None and m["improvement_percent"] > 0 for m in metrics
        ):
            raise DependencyError("no measured improvement supports this selected candidate")
        if candidate == "B0" and any(
            m["improvement_percent"] is not None and m["improvement_percent"] > 0 for m in metrics
        ):
            raise DependencyError("B0 choice conflicts with supplied improvement evidence")
        if candidate == "O3":
            for independent, source in (("O1", "W-PIPE"), ("O2", "W-SEARCH")):
                if not any(
                    r["candidate_variant"] == independent
                    and r["workload"] == source
                    and any(
                        m["status"] == "MEASURED"
                        and m["improvement_percent"] is not None
                        and m["improvement_percent"] > 0
                        for m in r["metrics"]
                    )
                    for r in reports
                ):
                    raise DependencyError(
                        "O3 requires independent O1/O2 improvements plus interaction evidence"
                    )
        choices[workload] = candidate
    return {"variants": choices, "sha256": receipt["content_sha256"]}
