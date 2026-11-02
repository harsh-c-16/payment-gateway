"""D-02/D-03 on real PostgreSQL: staging, I0/I1 equality, no-op, crash, resume, promotion."""

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest

from pipelines.catalog import load
from pipelines.catalog.adapter import ImportRefused, run_import
from pipelines.catalog.load import ImportReconciliationError
from pipelines.catalog.normalize import CsvStructureError
from pipelines.catalog.verify import verify_import
from tests.catalog.helpers import import_rows, row, write_csv

ROWS = [row(f"P{i:05}", discounted_price=str(100 + i)) for i in range(2500)]


def namespace():
    return "bench-h-" + uuid4().hex[:16]


def fetch(url, query, *parameters):
    with psycopg.connect(url) as connection:
        return connection.execute(query, parameters).fetchall()


def business(url, ns):
    return fetch(
        url,
        "SELECT sku,normalized_business_hash,catalog_version,price_minor,active FROM products "
        "WHERE namespace=%s ORDER BY sku",
        ns,
    )


def status(url, ns):
    rows = fetch(url, "SELECT status FROM catalog_imports WHERE namespace=%s", ns)
    return rows[0][0] if rows else None


def stage_rows(url, ns):
    return fetch(
        url,
        "SELECT s.source_row,s.sku,s.title,s.price_minor,s.attributes::text,s.image_urls::text,"
        "s.quality_flags,s.active,s.normalized_business_hash,s.source_crawled_at "
        "FROM catalog_stage s "
        "JOIN catalog_imports i USING (import_id) WHERE i.namespace=%s ORDER BY s.source_row",
        ns,
    )


def test_row_and_copy_produce_identical_rows_digests_and_chunks(tmp_path, database_url):
    first, second = namespace(), namespace()
    row_report, row_times = import_rows(tmp_path, database_url, first, ROWS, "row")
    copy_report, copy_times = import_rows(tmp_path, database_url, second, ROWS, "copy")
    assert row_report.canonical_business_digest == copy_report.canonical_business_digest
    assert stage_rows(database_url, first) == stage_rows(database_url, second)
    assert business(database_url, first) == business(database_url, second)
    assert row_report.chunk_count == copy_report.chunk_count == 3
    chunks = fetch(
        database_url,
        "SELECT chunk_no,row_count FROM catalog_import_chunks c JOIN catalog_imports i "
        "USING (import_id) WHERE i.namespace=%s ORDER BY chunk_no",
        first,
    )
    assert chunks == [(0, 1000), (1, 1000), (2, 500)]
    assert row_times["load_mode"] == "row" and copy_times["load_mode"] == "copy"
    assert row_times["stages"]["staging_seconds"] > 0
    assert copy_times["raw_to_ready_seconds"] > 0


def test_repeat_import_is_a_noop_with_same_versions(tmp_path, database_url):
    ns = namespace()
    rows = [row("A1"), row("A2", discounted_price="")]
    first, _ = import_rows(tmp_path, database_url, ns, rows)
    before = business(database_url, ns)
    second, timings = import_rows(tmp_path, database_url, ns, rows)
    assert (first.status, second.status) == ("promoted", "noop")
    assert second.inserted == second.updated == 0 and second.chunk_count == 0
    assert business(database_url, ns) == before
    assert all(item[2] == 1 for item in before)
    assert timings["status"] == "noop"


def test_changed_source_increments_only_changed_listings(tmp_path, database_url):
    ns = namespace()
    import_rows(tmp_path, database_url, ns, [row("A1"), row("A2")])
    report, _ = import_rows(
        tmp_path, database_url, ns, [row("A1", discounted_price="380"), row("A2"), row("A3")]
    )
    versions = {item[0]: item[2] for item in business(database_url, ns)}
    assert versions == {"FK-A1": 2, "FK-A2": 1, "FK-A3": 1}
    assert (report.inserted, report.updated, report.unchanged) == (1, 1, 1)


def test_removed_listing_becomes_inactive_not_deleted(tmp_path, database_url):
    ns = namespace()
    import_rows(tmp_path, database_url, ns, [row("A1"), row("A2")])
    import_rows(tmp_path, database_url, ns, [row("A1")])
    state = {item[0]: item[4] for item in business(database_url, ns)}
    assert state == {"FK-A1": True, "FK-A2": False}


class Boom(RuntimeError):
    pass


@pytest.mark.parametrize("mode", ["row", "copy"])
def test_interrupt_after_chunk_commit_then_resume(tmp_path, database_url, mode):
    ns = namespace()
    calls = []

    def die(stage):
        if stage == "after_chunk_commit":
            calls.append(stage)
            if len(calls) == 2:
                raise Boom

    with pytest.raises(Boom):
        import_rows(tmp_path, database_url, ns, ROWS, mode, hook=die)
    assert status(database_url, ns) == "staging"
    assert business(database_url, ns) == []
    assert len(stage_rows(database_url, ns)) == 2000
    report, _ = import_rows(tmp_path, database_url, ns, ROWS, mode)
    assert report.status == "promoted" and report.chunks_resumed == 2
    assert len(business(database_url, ns)) == 2500
    assert fetch(
        database_url,
        "SELECT count(*) FROM source_dispositions WHERE namespace=%s",
        ns,
    ) == [(2500,)]


def test_interrupt_before_promotion_leaves_nothing_ready(tmp_path, database_url):
    ns = namespace()

    def die(stage):
        if stage == "before_promotion":
            raise Boom

    with pytest.raises(Boom):
        import_rows(tmp_path, database_url, ns, [row("A1")], hook=die)
    assert status(database_url, ns) == "staging"
    assert business(database_url, ns) == []
    assert not (tmp_path / ns / "sku_manifest.json").exists()
    report, _ = import_rows(tmp_path, database_url, ns, [row("A1")])
    assert report.status == "promoted" and (tmp_path / ns / "sku_manifest.json").is_file()


@pytest.mark.parametrize("boundary", ["after_chunk_commit", "before_promotion"])
def test_process_death_at_named_boundary_then_resume(tmp_path, database_url, boundary):
    ns = namespace()
    source = write_csv(tmp_path / "source.csv", ROWS)
    out = tmp_path / ns
    child = subprocess.run(
        [
            sys.executable,
            "-m",
            "tests.catalog.import_crash",
            str(source),
            str(out),
            database_url,
            ns,
            boundary,
            "copy",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert child.returncode == 42, child.stderr
    assert f"BARRIER {boundary}" in child.stdout
    assert status(database_url, ns) == "staging"
    assert business(database_url, ns) == []
    report, _ = run_import(source, load_mode="copy", namespace=ns, out=out, url=database_url)
    assert report.status == "promoted"
    assert report.chunks_resumed == (2 if boundary == "after_chunk_commit" else 3)
    assert len(business(database_url, ns)) == 2500


def test_concurrent_imports_serialize_into_one_promotion(tmp_path, database_url):
    ns = namespace()
    source = write_csv(tmp_path / "source.csv", ROWS)

    def one(index):
        return run_import(
            source, load_mode="copy", namespace=ns, out=tmp_path / f"{ns}-{index}", url=database_url
        )[0].status

    with ThreadPoolExecutor(2) as pool:
        results = sorted(pool.map(one, range(2)))
    assert results == ["noop", "promoted"]
    assert len(business(database_url, ns)) == 2500


def test_tampered_staged_chunk_blocks_promotion(tmp_path, database_url):
    ns = namespace()

    def die(stage):
        if stage == "before_promotion":
            raise Boom

    with pytest.raises(Boom):
        import_rows(tmp_path, database_url, ns, [row("A1"), row("A2")], hook=die)
    with psycopg.connect(database_url) as connection:
        connection.execute("UPDATE catalog_stage SET normalized_business_hash=repeat('0',64)")
    with pytest.raises(ImportReconciliationError):
        import_rows(tmp_path, database_url, ns, [row("A1"), row("A2")])
    assert business(database_url, ns) == []


def test_changed_catalog_parquet_is_refused(tmp_path, database_url, monkeypatch):
    ns = namespace()
    real = load.read_canonical_rows

    def tampered(out, manifest):
        (out / manifest.files.catalog.path).write_bytes(b"not parquet")
        return real(out, manifest)

    monkeypatch.setattr(load, "read_canonical_rows", tampered)
    with pytest.raises(ValueError, match="manifest hash"):
        import_rows(tmp_path, database_url, ns, [row("A1")])
    assert business(database_url, ns) == []


def test_bound_failure_reports_locator_and_promotes_nothing(tmp_path, database_url):
    ns = namespace()
    rows = [row("A1"), row("A2", description="x" * 16385)]
    with pytest.raises(ImportRefused):
        import_rows(tmp_path, database_url, ns, rows)
    failure = json.loads((tmp_path / ns / "import_failure.json").read_text(encoding="utf-8"))
    assert failure["failures"] == [{"reason": "INPUT_BOUND_EXCEEDED", "source_row_number": 2}]
    assert status(database_url, ns) is None


def test_malformed_csv_promotes_nothing(tmp_path, database_url):
    ns = namespace()
    path = tmp_path / "bad.csv"
    path.write_text("pid,product_name\nONLY_ONE_COLUMN\n", encoding="utf-8")
    with pytest.raises(CsvStructureError):
        run_import(path, load_mode="copy", namespace=ns, out=tmp_path / ns, url=database_url)
    assert status(database_url, ns) is None


def test_equal_time_conflict_is_withheld(tmp_path, database_url):
    ns = namespace()
    rows = [row("A1", uniq_id="a"), row("A1", uniq_id="b", discounted_price="380"), row("A2")]
    import_rows(tmp_path, database_url, ns, rows)
    assert [item[0] for item in business(database_url, ns)] == ["FK-A2"]
    dispositions = fetch(
        database_url,
        "SELECT disposition,issue_codes FROM source_dispositions "
        "WHERE namespace=%s ORDER BY row_no",
        ns,
    )
    assert dispositions[0][0] == dispositions[1][0] == "rejected_mandatory"
    assert "SOURCE_ID_CONFLICT" in dispositions[0][1]


def test_full_file_import_row_and_copy_then_verify(tmp_path, database_url, source_csv):
    reports = {}
    for mode in ("row", "copy"):
        ns = namespace()
        out = tmp_path / ns
        reports[mode], _ = run_import(
            source_csv, load_mode=mode, namespace=ns, out=out, url=database_url
        )
        with psycopg.connect(database_url, autocommit=True) as connection:
            checks = verify_import(
                out / "normalized_manifest.json", ns, connection, source_path=source_csv
            )
        failed = [item["name"] for item in checks["assertions"] if not item["passed"]]
        assert not failed
        assert checks["provider_normalization_comparison"] == "PASS"
        assert checks["facet_coverage_verification"] == "PASS"
        manifest = json.loads((out / "sku_manifest.json").read_text(encoding="utf-8"))
        assert manifest["sku_count"] == 19920
        assert len(json.loads((out / "facet_dictionary.json").read_text())["roots"]) == 32
        assert (out / "facet_dictionary.json").stat().st_size < 2 * 1024 * 1024
    assert reports["row"].canonical_business_digest == reports["copy"].canonical_business_digest
    assert reports["row"].active_rows == 19920 and reports["row"].inactive_rows == 78
