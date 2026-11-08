"""Saved M4 audit mappings replay the same independent oracle from raw evidence."""

from benchmarks.quality_binding import verify_review
from projectctl.providers import DependencyError


def recheck(directory, context, expected):
    from benchmarks.performance import read_json
    from projectctl.artifacts import file_hash

    # verify_review accepts repository-relative paths only, just like the live binding.
    from projectctl.config import ROOT

    review = verify_review((directory / "binding_review.json").relative_to(ROOT).as_posix())
    required = {
        "benchmarks/analytics_recheck.py",
        "benchmarks/pipeline_audit.py",
        "infra/analytics_runtime.py",
        "infra/analytics_resources.py",
        "pipelines/ingestion/adapters.py",
    }
    if not required <= {ref["path"] for ref in review["contracts"]}:
        raise DependencyError("saved M4 audit requires the concrete mapping review")
    if (
        expected["namespace"] != context["namespace"]
        or expected["audit_kind"] != context["workload_id"]
    ):
        raise DependencyError("saved M4 audit context mismatch")
    if expected["audit_kind"] == "W-PIPE":
        from benchmarks.pipeline_audit import audit_pipeline

        binding = review | {"namespace": context["namespace"]}
        # Source review was already hash-verified above; this is a derived scope binding.
        binding["review_sha256"] = file_hash(directory / "binding_review.json")
        raw = read_json(directory / "analytics_raw_evidence.json")
        if raw.get("test_mode") != "real":
            raise DependencyError("saved M4 recheck refuses test-double exports")
        return audit_pipeline(context, directory, raw, review=binding, persist=False)
    if expected["audit_kind"] != "W-QUALITY":
        raise DependencyError("unknown M4 audit kind")
    from benchmarks.composition import catalog_projection
    from benchmarks.quality_audit import reconcile_quality
    from benchmarks.workloads import generate_workload
    from projectctl.models import EvaluationConfig

    config = EvaluationConfig.model_validate(read_json(directory / "resolved_config.json"))
    projection = catalog_projection(config)
    recipe = generate_workload("W-QUALITY", config.generator.seed, projection).as_dict()
    if (
        expected["seed"] != config.generator.seed
        or expected["run_id"] != context["run_id"]
        or expected["dataset_revision"] != projection["dataset_revision"]
        or expected["selected_skus"] != recipe["selected_skus"]
    ):
        raise DependencyError("saved quality inputs differ from the frozen catalogue/recipe")
    raw = read_json(directory / "quality_raw_audit.json")
    if raw.get("test_mode") != "real":
        raise DependencyError("saved M4 recheck refuses test-double exports")
    if read_json(directory / "observed.json")["raw_audit_sha256"] != file_hash(
        directory / "quality_raw_audit.json"
    ):
        raise DependencyError("saved quality raw audit hash differs from its projection")
    raw["binding_review_verified"] = True
    return reconcile_quality(context | expected, directory, raw)
