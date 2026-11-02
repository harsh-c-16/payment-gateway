"""projectctl bindings for `catalog profile|import|verify` (runbook §§2-3)."""

import csv
import hashlib
import json
import os
from pathlib import Path
from time import perf_counter

import psycopg

from pipelines.catalog import artifacts, load, verify
from pipelines.catalog.migrate import migrate_catalog
from pipelines.catalog.normalize import (
    CsvStructureError,
    load_dictionary,
    normalize_catalog_row,
    profile_catalog,
    read_source,
    select_latest_listings,
)
from projectctl.models import ExitCode
from projectctl.providers import ProviderResult
from shared.event_transport.schemas import canonical_json
from shared.telemetry.metrics import Telemetry


class ImportRefused(ValueError):
    """Bound failure: reported with its source locator, nothing is promoted."""


def database_url():
    url = os.environ.get("CATALOG_DATABASE_URL")
    if url:
        return url
    from infra import postgres

    return postgres.database_url("catalog", postgres.credentials())


def store_root():
    return os.environ.get("LAKEHOUSE_ROOT") or "artifacts/lakehouse"


def read_all(source, dictionary):
    raw_rows, observations = [], []
    for number, raw in read_source(source, dictionary):
        raw_rows.append(raw)
        observations.append(normalize_catalog_row(raw, number, dictionary))
    return raw_rows, observations


def _bound_failures(observations):
    return [
        {"reason": "INPUT_BOUND_EXCEEDED", "source_row_number": item.row_number}
        for item in observations
        if item.bound_exceeded
    ]


def write_profile(out, raw_rows, observations, selection, source_sha256):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    profile = profile_catalog(raw_rows, selection, observations, source_sha256)
    artifacts.write_json(out / "profile.json", profile)
    rows = artifacts.quality_by_category_rows(selection, observations)
    names = ["canonical", "active", "known_brand", "known_description", "known_colour"]
    names += ["known_material", "known_size", "issues"]
    with (out / "quality_by_category.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["category", *names])
        for category in sorted(rows):
            writer.writerow([category, *(rows[category][name] for name in names)])
    return profile


def write_import_metrics(out, profile, stages, load_mode, report):
    """Common §14 names. A finite job has no scrape target, so they are saved for the collector."""
    metrics = Telemetry(
        label_values={
            "disposition": set(profile["selected_counts"]),
            "reason": set(profile["issue_counts"]),
            "stage": set(stages),
            "mode": {"row", "copy"},
        }
    )
    for disposition, count in profile["selected_counts"].items():
        metrics.record("catalog_source_rows_total", count, disposition=disposition)
    for reason, count in profile["issue_counts"].items():
        metrics.record("catalog_issues_total", count, reason=reason)
    for stage, seconds in stages.items():
        metrics.record("catalog_import_duration_seconds", seconds, stage=stage)
    staging = stages.get("staging_seconds")
    if staging:
        metrics.record(
            "catalog_import_rows_per_second", report.canonical_rows / staging, mode=load_mode
        )
    (out / "import_metrics.prom").write_bytes(metrics.exposition())


def run_import(source, *, load_mode, namespace, out, url=None, hook=lambda stage: None):
    """Raw file open to catalogue/manifest readiness; the W-IMPORT measurement boundary."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    timer, stages, cpu_start = perf_counter(), {}, os.times()

    def mark(name, started):
        stages[name] = perf_counter() - started

    started = timer
    dictionary = load_dictionary()
    data = Path(source).read_bytes()
    source_sha256 = hashlib.sha256(data).hexdigest()
    archive = artifacts.archive_source(store_root(), source, data, source_sha256)
    del data
    mark("read_archive_seconds", started)
    started = perf_counter()
    raw_rows, observations = read_all(source, dictionary)
    selection = select_latest_listings(observations)
    mark("parse_normalize_select_seconds", started)
    failures = _bound_failures(observations)
    if failures:
        artifacts.write_json(out / "import_failure.json", {"failures": failures})
        raise ImportRefused(json.dumps(failures[0]))
    started = perf_counter()
    source_manifest = artifacts.write_source_manifest(
        out, source, archive, source_sha256, len(raw_rows), dictionary
    )
    manifest = artifacts.write_normalized(out, source_manifest, raw_rows, observations, selection)
    facets = artifacts.facet_dictionary(selection, manifest, dictionary)
    facets_document = facets.model_dump(mode="json")
    artifacts.write_json(out / "facet_dictionary.json", facets_document)
    profile = write_profile(out, raw_rows, observations, selection, source_sha256)
    mark("artifact_seconds", started)
    observation_rows = [
        (
            item.row_number,
            item.uniq_id,
            item.pid,
            hashlib.sha256(canonical_json(raw)).hexdigest(),
            item.mandatory_valid,
        )
        for item, raw in zip(observations, raw_rows, strict=True)
    ]
    disposition_rows = [
        (item.row_number, selection.dispositions[item.row_number], sorted(set(item.issues)))
        for item in observations
    ]
    wal_before = None
    with psycopg.connect(url or database_url(), autocommit=True, connect_timeout=5) as connection:
        with connection.transaction():
            migrate_catalog(connection)
        wal_before = connection.execute("SELECT pg_current_wal_lsn()").fetchone()[0]
        report = load.load_catalog(
            connection,
            out=out,
            source_manifest=source_manifest,
            manifest=manifest,
            load_mode=load_mode,
            namespace=namespace,
            observations=observation_rows,
            dispositions=disposition_rows,
            facets=facets_document,
            issue_counts=profile["issue_counts"],
            hook=hook,
        )
        started = perf_counter()
        sku_manifest = load.export_sku_manifest(connection, manifest, namespace, source_sha256)
        artifacts.write_json(out / "sku_manifest.json", sku_manifest)
        mark("export_seconds", started)
        wal_bytes = connection.execute(
            "SELECT pg_wal_lsn_diff(pg_current_wal_lsn(), %s)", (wal_before,)
        ).fetchone()[0]
    for name, milliseconds in report.elapsed_by_stage_ms.items():
        stages[name.removesuffix("_ms") + "_seconds"] = milliseconds / 1000
    raw_to_ready = perf_counter() - timer
    times = os.times()
    timings = {
        "raw_to_ready_seconds": raw_to_ready,
        "stages": stages,
        "load_mode": load_mode,
        "status": report.status,
        "chunk_rows": load.CHUNK_ROWS,
        "chunk_count": report.chunk_count,
        "chunks_resumed": report.chunks_resumed,
        "raw_rows": report.raw_rows,
        "canonical_rows": report.canonical_rows,
        "active_rows": report.active_rows,
        "client_cpu_seconds": times.user + times.system - cpu_start.user - cpu_start.system,
        "client_peak_rss_kib": artifacts.peak_rss_kib(),
        "wal_bytes": int(wal_bytes),
        "logical_digest": report.canonical_business_digest,
    }
    artifacts.write_json(out / "import_timings.json", timings)
    write_import_metrics(out, profile, stages, load_mode, report)
    report = report.model_copy(update={"artifact_paths": sorted(p.name for p in out.iterdir())})
    artifacts.write_json(out / "load_report.json", report.model_dump(mode="json"))
    return report, timings


def profile_action(invocation):
    arguments = invocation.arguments
    try:
        dictionary = load_dictionary()
        raw_rows, observations = read_all(arguments["source"], dictionary)
        selection = select_latest_listings(observations)
        source_sha256 = hashlib.sha256(Path(arguments["source"]).read_bytes()).hexdigest()
        profile = write_profile(arguments["out"], raw_rows, observations, selection, source_sha256)
    except OSError as error:
        return ProviderResult(ExitCode.BAD_INPUT, (type(error).__name__,), "real")
    except CsvStructureError as error:
        return ProviderResult(ExitCode.BAD_INPUT, (str(error),), "real")
    return ProviderResult(
        ExitCode.COMPLETED, (f"profile written: {json.dumps(profile['selected_counts'])}",), "real"
    )


def import_action(invocation):
    arguments = invocation.arguments
    try:
        report, _ = run_import(
            arguments["source"],
            load_mode=arguments["load_mode"],
            namespace=arguments["namespace"],
            out=arguments["out"],
        )
    except (CsvStructureError, ImportRefused, FileNotFoundError) as error:
        return ProviderResult(ExitCode.BAD_INPUT, (str(error),), "real")
    except load.ImportReconciliationError as error:
        return ProviderResult(ExitCode.CORRECTNESS_FAILURE, (str(error),), "real")
    except psycopg.Error as error:
        return ProviderResult(ExitCode.DEPENDENCY_FAILURE, (type(error).__name__,), "real")
    return ProviderResult(
        ExitCode.COMPLETED,
        (
            f"{report.status}: canonical={report.canonical_rows} active={report.active_rows} "
            f"inactive={report.inactive_rows} digest={report.canonical_business_digest}",
        ),
        "real",
    )


def verify_action(invocation):
    arguments = invocation.arguments
    try:
        with psycopg.connect(database_url(), autocommit=True, connect_timeout=5) as connection:
            report = verify.verify_import(
                Path(arguments["manifest"]), arguments["namespace"], connection
            )
    except (OSError, ValueError) as error:
        return ProviderResult(ExitCode.BAD_INPUT, (type(error).__name__,), "real")
    except psycopg.Error as error:
        return ProviderResult(ExitCode.DEPENDENCY_FAILURE, (type(error).__name__,), "real")
    failed = [item["name"] for item in report["assertions"] if not item["passed"]]
    if failed:
        return ProviderResult(ExitCode.CORRECTNESS_FAILURE, tuple(failed), "real")
    return ProviderResult(
        ExitCode.COMPLETED, (f"verified {len(report['assertions'])} assertions",), "real"
    )


def register(registry):
    registry.register("catalog profile", profile_action)
    registry.register("catalog import", import_action)
    registry.register("catalog verify", verify_action)
