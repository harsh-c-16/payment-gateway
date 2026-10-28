"""P3 offline fixture action; does not register a provider or benchmark double."""

from benchmarks.fixtures import build_bundle
from projectctl.models import ExitCode
from projectctl.providers import ProviderResult


def build(invocation):
    from projectctl.config import ROOT, repo_path

    target = repo_path(invocation.config.artifacts.root) / "fixtures" / invocation.run_id
    try:
        index = build_bundle(ROOT, target, invocation.config, invocation.arguments["seed"])
    except (OSError, ValueError, KeyError) as error:
        return ProviderResult(
            ExitCode.CORRECTNESS_FAILURE,
            (
                f"offline fixture build failed: {type(error).__name__}; partial evidence retained",
                target.relative_to(ROOT).as_posix(),
            ),
            "offline",
        )
    code = (
        ExitCode.CORRECTNESS_FAILURE
        if index["dataset_checks_status"] == "FAIL"
        else ExitCode.COMPLETED
    )
    if index["dataset_checks_status"] == "INCOMPLETE":
        code = ExitCode.DEPENDENCY_FAILURE
    return ProviderResult(
        code,
        (
            "offline expectations only; no Kafka/API/model execution",
            "fixture bundle: " + target.relative_to(ROOT).as_posix(),
            "W-QUALITY logical counts: 98500 valid +1000 duplicates +500 invalid =100000",
            "60 draft assistant scenarios; human review and provider binding pending; "
            "quality NOT_RUN",
            "independent source check: " + index["dataset_checks_status"],
        ),
        "offline",
    )
