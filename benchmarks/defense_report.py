"""Rebuild the viva report from hashed measurements and explicitly sourced evidence."""

import argparse
import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from statistics import median

from benchmarks.defense import fingerprint, stats
from benchmarks.windows.evidence import ROOT, digest, write


def verified_run(directory):
    manifest = json.loads((directory / "manifest.json").read_text("utf-8"))
    if manifest["status"] != "MEASURED_COMPONENT" or manifest.get("formal_p9_qualified"):
        raise ValueError("Only completed component evidence; never promote to formal P9")
    for name, expected in manifest["files"].items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()) or digest(path) != expected:
            raise ValueError("Evidence path/hash differs")
    if not json.loads((directory / "cleanup.json").read_text())["container_removed"]:
        raise ValueError("Disposable database cleanup not verified")
    return manifest


def aggregate(samples, repetitions=3):
    groups = defaultdict(lambda: defaultdict(list))
    for row in samples:
        groups[(row["layout"], row["query"], row["variant"])][row["repetition"]].append(row)
    result = {}
    for key, reps in groups.items():
        if set(reps) != set(range(1, repetitions + 1)):
            raise ValueError("Incomplete paired repetitions")
        if len({len(rows) for rows in reps.values()}) != 1:
            raise ValueError("Unequal samples per repetition")
        if len({r["result_sha256"] for rows in reps.values() for r in rows}) != 1:
            raise ValueError("Logical results differ within a comparator")
        per_rep = [stats([r["seconds"] * 1000 for r in reps[i]]) for i in range(1, repetitions + 1)]
        result[key] = {
            "repetition_medians_ms": [r["median"] for r in per_rep],
            "median_ms": median(r["median"] for r in per_rep),
            "p95_ms": stats([r["seconds"] * 1000 for rows in reps.values() for r in rows])["p95"],
            "samples": sum(len(rows) for rows in reps.values()),
            "result_sha256": next(iter(reps.values()))[0]["result_sha256"],
            "plan_nodes": [r["Node Type"] for r in next(iter(reps.values()))[0]["plan"]],
            "indexes_used": sorted(
                {
                    node["Index Name"]
                    for rows in reps.values()
                    for node in rows[0]["plan"]
                    if "Index Name" in node
                }
            ),
        }
    # Match logical results across methods, not just repetitions of one method.
    for layout, query, _ in result:
        if (
            len(
                {
                    v["result_sha256"]
                    for (lay, q, _), v in result.items()
                    if lay == layout and q == query
                }
            )
            != 1
        ):
            raise ValueError("Alternative index changed logical results")
    return result


def checked_record(path):
    record = json.loads(path.read_text("utf-8"))
    run = record.get("run", record)
    checks = run.get("checks", [])
    if (
        run.get("status") != "Passed"
        or not checks
        or any(
            c.get("passed") is not True
            or c.get("observed") is None
            or fingerprint(c.get("expected")) != fingerprint(c.get("observed"))
            for c in checks
        )
    ):
        raise ValueError("Saved status/checks do not establish a pass: " + str(path))
    return run


def edge_evidence(directory):
    result = []
    for scenario in (
        "duplicate",
        "conflict",
        "malformed",
        "out_of_order",
        "late_event",
        "replay",
        "race",
    ):
        path = directory / (scenario + ".json")
        run = checked_record(path)
        if run["scenario"] != scenario:
            raise ValueError("Scenario identity differs")
        if scenario == "race":
            orders = run["orders"]
            winners = [o for o in orders if o["status"] == "CONFIRMED"]
            losers = [o for o in orders if o["status"] == "CANCELLED"]
            debits = [e for e in run["ledger"] if e["kind"] == "DEBIT"]
            if len(winners) != 1 or len(losers) != 1 or len(debits) != 1:
                raise ValueError("Independent saved race conservation failed")
            if (debits[0]["order_id"], debits[0]["amount_minor"]) != (
                winners[0]["order_id"],
                winners[0]["total_amount_minor"],
            ):
                raise ValueError("Saved race debit identity/amount differs")
        elif scenario == "out_of_order":
            if (run["projected_stock"]["stock_version"], run["projected_stock"]["available"]) != (
                2,
                4,
            ):
                raise ValueError("Saved projection was overwritten by stale stock")
        result.append(
            {
                "scenario": scenario,
                "checks": len(run["checks"]),
                "elapsed_seconds": run.get("elapsed_seconds"),
                "started_at": run["started_at"],
                "run_id": run["id"],
                "source": path.relative_to(ROOT).as_posix(),
                "sha256": digest(path),
            }
        )
    return result


def pytest_counts(path):
    root = ET.parse(path).getroot()
    suites = list(root) if root.tag == "testsuites" else [root]
    counts = {
        name: sum(int(s.get(name, 0)) for s in suites)
        for name in ("tests", "failures", "errors", "skipped")
    }
    counts["passed"] = counts["tests"] - sum(counts[k] for k in ("failures", "errors", "skipped"))
    return counts


def build(directory, junit, refund_dir, destination):
    manifest = verified_run(directory)
    samples = json.loads((directory / "index-samples.json").read_text())
    costs = json.loads((directory / "index-costs.json").read_text())
    summary = json.loads((directory / "retention.json").read_text())
    index = aggregate(samples)
    checks = pytest_counts(junit)
    edges = edge_evidence(ROOT / "artifacts/journey-guided-browser/1794666758168")
    failures = {}
    for path in sorted((ROOT / "artifacts/failure-demo").glob("*/evidence.json")):
        run = checked_record(path)
        key = run["scenario"] + "/" + run["mode"]
        if key not in failures or run["completed_at"] > failures[key][0]["completed_at"]:
            failures[key] = (run, path)
    refunds = list(refund_dir.glob("*/evidence.json"))
    if refunds:
        run = checked_record(refunds[-1])
        failures["refund/automated"] = (run, refunds[-1])
    old_dir = ROOT / "artifacts/windows/09aba659a2104d99b5e6c3e8f8ebbd1b"
    old = json.loads((old_dir / "manifest.json").read_text())
    journal = old_dir / "measurements.jsonl"
    if digest(journal) != old["files"]["measurements.jsonl"]:
        raise ValueError("Prior diagnostic journal hash differs")
    old_rows = [json.loads(line) for line in journal.read_text().splitlines()]
    index_rows = [
        {"layout": k[0], "query": k[1], "variant": k[2], **v} for k, v in sorted(index.items())
    ]
    summary_latency = {
        variant: median(
            median(
                r["seconds"]
                for r in summary["timings"]
                if r["variant"] == variant and r["repetition"] == rep
            )
            for rep in (1, 2, 3)
        )
        for variant in ("raw", "summary")
    }
    summary_change = 100 * (summary_latency["summary"] / summary_latency["raw"] - 1)
    report_data = {
        "status": "MEASURED_COMPONENT",
        "formal_p9_qualified": False,
        "index": index_rows,
        "retention": summary,
        "edge_cases": edges,
        "pytest": {**checks, "source": junit.relative_to(ROOT).as_posix(), "sha256": digest(junit)},
        "failure_cases": [
            {
                "scenario": key,
                "checks": len(run["checks"]),
                "run_id": run["id"],
                "source": path.relative_to(ROOT).as_posix(),
                "sha256": digest(path),
                "completed_at": run["completed_at"],
            }
            for key, (run, path) in sorted(failures.items())
        ],
        "prior_provider_status": old["status"],
        "prior_provider_observations": len(old_rows),
    }
    write(directory / "defense-report.json", report_data)
    rel = directory.relative_to(ROOT).as_posix()
    rows = [
        "# Professor demo: questions, tests and measured evidence",
        "",
        "Generated from retained raw observations on " + manifest["completed_at"] + ".",
        "",
        "## What we can defend",
        "",
        "- Keep summaries **alongside** audit/replay data. The new experiment tests the "
        "space/query trade-off, not a production deletion policy.",
        "- Index choice depends on predicates and physical layout. B-tree, hash, BRIN and "
        "GIN were measured separately; no single index wins every workload.",
        "- The seven previously executed real pipeline cases were rechecked from saved "
        "evidence. Existing transaction recovery cases and the new refund attempt are "
        "listed separately below.",
        f"- Current focused correctness suite: **{checks['passed']} passed, "
        f"{checks['failures']} failed, {checks['errors']} errors, {checks['skipped']} skipped**. "
        "These counts establish correctness coverage, not throughput.",
        "",
        "## Measurement scope and controls",
        "",
        f"Evidence: `{rel}`. Seed {manifest['seed']}; three randomized repetitions, "
        f"three warmups and {manifest['samples_per_query_per_repetition']} timed calls per "
        "query/method/repetition. Tables show the median of three repetition medians; "
        "raw samples, p95, all repetition medians, plans and hashes are in defense-report.json.",
        "",
        "Original CSV: 20,000 observations, 19,998 canonical listings, 19,920 active. "
        "The probe reuses production normalization/selection and preserves unknown categories. "
        "It measures a **title/category/price projection**, not the production search API, "
        "stock joins, hybrid ranking or embedding inference.",
        "",
        "PostgreSQL: pinned image, 1 CPU, 512 MiB limit, 256 MiB tmpfs; durability "
        "settings enabled. DuckDB: one thread, 64 MiB query memory. Host: "
        f"{manifest['host']['cpu_model'][0]}, Windows, "
        f"{manifest['host']['total_memory_bytes'] / 2**30:.1f} GiB RAM. "
        f"Pre-existing Docker containers: {len(manifest['existing_containers'].splitlines())}. "
        "Host background activity and "
        "warm RAM-backed SQL timings limit generalization. **Not formal P9, SSD, "
        "cold-cache, stress-capacity or end-to-end latency evidence.** No production "
        "index changed.",
        "",
        "## Q1. Why retain summaries instead of simply deleting old entries?",
        "",
        f"Controlled DuckDB example: {summary['raw_rows']:,} synthetic immutable events "
        f"became {summary['summary_rows']:,} minute/type summaries. Same Zstandard codec: "
        f"raw **{summary['raw_bytes']:,} bytes**, summaries **{summary['summary_bytes']:,} bytes** "
        f"({100 * (1 - summary['summary_bytes'] / summary['raw_bytes']):.2f}% fewer bytes). "
        "Counts and integer monetary sums match an independent Python oracle in every trial.",
        "",
        "| Aggregate query | Rep 1 median ms | Rep 2 | Rep 3 | Median ms |",
        "|---|---:|---:|---:|---:|",
    ]
    for variant in ("raw", "summary"):
        values = [
            median(
                r["seconds"] * 1000
                for r in summary["timings"]
                if r["variant"] == variant and r["repetition"] == rep
            )
            for rep in (1, 2, 3)
        ]
        rows.append(
            f"| {variant} | "
            + " | ".join(f"{v:.3f}" for v in values)
            + f" | {median(values):.3f} |"
        )
    rows += [
        "",
        f"One-off rollup construction: {summary['summary_build_seconds'] * 1000:.3f} ms. "
        f"Rollup query latency was {abs(summary_change):.2f}% "
        f"{'higher' if summary_change >= 0 else 'lower'} in this small warm experiment. "
        "Do not infer latency from the space saving alone. Compression, workload "
        "and scale matter.",
        "",
        "Counterexample: histories `(E1=100,E2=200)` and `(E1=200,E2=100)` both "
        "have count 2 and sum 300, but disagree on each event's amount. A rollup cannot "
        "recover exact lineage, diagnose a wrong debit or reconstruct arbitrary new queries. "
        "Compaction preserves rows; aggregation deliberately loses detail.",
        "",
        "**Current policy:** Kafka/published outbox default 7 days; Bronze, dedup keys, "
        "manifests and evidence at least 30 days and until evaluation acceptance, whichever "
        "is later; replay references block deletion. Cleanup is explicit and disabled during "
        "experiments. FileStore.list_orphans inventories files; it does not delete them. "
        "No summary-only purge or production TTL was introduced by these tests.",
        "",
        "## Q2. Can we delete old deduplication IDs once totals are summarized?",
        "",
        f"Actual isolated DuckDB policy probe: replaying E1 twice with retained IDs "
        f"created **{summary['duplicate_effects_with_retained_ids']}** logical contribution. "
        "Deleting its seen-ID before replay created "
        f"**{summary['duplicate_effects_after_unsafe_id_retirement']}**. "
        "The second policy is an intentionally unsafe counterexample, not production behavior. "
        "Dedup lifetime must cover supported redelivery/replay horizons; old totals alone "
        "do not establish whether a replayed ID was already counted.",
        "",
        "## Q3-Q5. Why B-tree? Did hash, BRIN or GIN do better?",
        "",
        "The integrity primary key remains in every variant. `none` means no additional "
        "candidate index. B-tree uses (namespace, category, price); hash uses category equality; "
        "BRIN uses category/price with pages_per_range=4; GIN uses a title tsvector. "
        "The lexical comparator keeps the same SQL and title vector on both sides. This is "
        "a separately labelled extension, not a change to frozen B0/O2 semantics.",
        "",
        "| Shuffled physical layout / client query ms | No optional index | B-tree | Hash "
        "| BRIN | GIN |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for query in (
        "category_price",
        "category_broad",
        "category_rare",
        "price_range",
        "lexical_shirt",
        "lexical_wristwatch",
    ):
        rows.append(
            f"| {query} | "
            + " | ".join(
                f"{index['shuffled', query, v]['median_ms']:.3f}"
                for v in ("none", "btree", "hash", "brin", "gin")
            )
            + " |"
        )
    rows += [
        "",
        "**Interpretation:** B-tree suits category equality plus price range/order. Hash "
        "is an equality comparator, not a range/order replacement. GIN addresses text membership, "
        "not price ordering. BRIN summarizes block ranges and depends on correlation. Planner "
        "choices were not forced; saved plans show where it chose a sequential scan. "
        "The lexical wristwatch query is a zero-hit case (see plan Actual Rows), so its speed "
        "does not establish positive-hit ranking quality. All response digests are identical "
        "across variants and layouts.",
        "",
        "[PostgreSQL index capabilities](https://www.postgresql.org/docs/18/indexes-types.html) "
        "and [multicolumn ordering](https://www.postgresql.org/docs/18/indexes-multicolumn.html) "
        "explain the mechanisms; the numbers above come from our own experiment.",
        "",
        "### Does sorting the data change the BRIN result?",
        "",
        "| Price-range count / client query ms | No optional index | B-tree | BRIN |",
        "|---|---:|---:|---:|",
    ]
    for layout in ("shuffled", "price_sorted"):
        rows.append(
            f"| {layout} | "
            + " | ".join(
                f"{index[layout, 'price_range', v]['median_ms']:.3f}"
                for v in ("none", "btree", "brin")
            )
            + " |"
        )
    rows += [
        "",
        "Sorting/rewriting cost is not included in these read times. Do not claim a "
        "free BRIN improvement or cluster the live catalogue based on this probe.",
        "",
        "## Q6. What do the indexes cost to build and maintain?",
        "",
        "Median of three shuffled-layout trials. The write probe updates the same 100 "
        "prices inside a rollback-only transaction; WAL is still generated. It measures the "
        "UPDATE statement, not commit/fsync latency. Vacuum/analyze follows every variant; "
        "write probes and rollback can affect physical pages, another exploratory limitation.",
        "",
        "| Additional index | KiB | Build ms | Build WAL KiB | 100-price UPDATE ms | "
        "UPDATE WAL KiB |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for variant in ("none", "btree", "hash", "brin", "gin"):
        records = [r for r in costs if r["layout"] == "shuffled" and r["variant"] == variant]
        values = [
            median(r[k] for r in records) * scale
            for k, scale in (
                ("index_bytes", 1 / 1024),
                ("build_seconds", 1000),
                ("build_wal_bytes", 1 / 1024),
                ("update_100_seconds", 1000),
                ("update_100_wal_bytes", 1 / 1024),
            )
        ]
        rows.append(f"| {variant} | " + " | ".join(f"{v:.3f}" for v in values) + " |")
    rows += [
        "",
        "GIN's text-maintenance cost is **not** established by a price-only update. "
        "The experiment neither changes descriptions nor measures mixed write throughput.",
        "",
        "## Q7. Why batching, COPY and compaction? Are those comparisons already done?",
        "",
        "Existing implementation and tests were reused, not replaced: "
        "benchmarks/windows/measure.py compares row INSERT/COPY, batch 1/100, B0/O2 and "
        "small-file/compacted Q1-Q6 outputs. Its raw observation journal has "
        f"**{len(old_rows)} observations**, verified against the original manifest hash. "
        f"The original run status is **{old['status']}**. Its resource collector failed; "
        "the diagnostic report explicitly says NOT QUALIFIED. No percentages from it are "
        "promoted into a claim that an optimization is proven.",
        "",
        "[Existing Windows protocol](WINDOWS_MEASUREMENTS.md) defines the timed boundaries. "
        "The sink comparison excludes Kafka transport/accumulation waiting; SQL indexing "
        "excludes HTTP. The existing end_to_end.py runner measures real HTTP/Kafka/active Gold, "
        "but a complete newly qualified run is NOT_RUN here. Partition/consumer scaling, "
        "stress saturation and full integrated B0/C-BEST also remain NOT_RUN in this report.",
        "",
        "[Harsh's owner-run experiments](../harsh/experiments.md) already cover COPY, "
        "statistics, B-tree, compaction and exact/HNSW. They are attributed owner results "
        "on another host; their raw bundles are absent here. The owner reported ANN recall "
        "0.906 and did not adopt HNSW at this size. This is not a new independently verified "
        "ANN result. Do not imply that all alternatives were reproduced locally.",
        "",
        "## Q8-Q10. What happens to duplicates, bad data, late events and the last unit?",
        "",
        "Retained **real Kafka + owner services + active Gold** runs, originally exercised "
        "through the guided browser. Revalidated now from saved checks and observed values; "
        "this is evidence reuse, not a claim that seven fresh transactions were executed. "
        "Fixture elapsed time includes setup/waits and is not service or end-to-end latency.",
        "",
        "| Case | Verified result | Checks | Fixture elapsed s |",
        "|---|---|---:|---:|",
    ]
    descriptions = {
        "duplicate": "3 deliveries, 2 logical valid IDs, 1 duplicate; one contribution per ID",
        "conflict": "Changed contents under same ID rejected as EVENT_ID_CONFLICT",
        "malformed": "1 invalid JSON quarantined; both valid neighbors reach Gold",
        "out_of_order": "v2/4 units survives later v1/9 units; stale projection rejected",
        "late_event": "Earlier window revised from 1 to 2 events in a newer Gold generation",
        "replay": "Original/replay business equality; repeat replay preserves logical effect",
        "race": "2 checkouts, 1 sale, 1 cancellation, 1 matching debit; both orders in Gold",
    }
    for edge in edges:
        rows.append(
            f"| {edge['scenario']} | {descriptions[edge['scenario']]} | "
            f"{edge['checks']} | {edge['elapsed_seconds']:.3f} |"
        )
    rows += [
        "",
        "The race's debit identity/amount and the stock-version result were additionally "
        "recomputed from saved order/ledger/projection facts. Download paths, hashes and run "
        "IDs are indexed in defense-report.json. Exactly-once **logical effects** do not mean "
        "exactly-once Kafka delivery. Search stock is advisory; Inventory owns reservations.",
        "",
        "## Q11-Q12. What if a response is lost, a service crashes, or payment arrives late?",
        "",
        "Selected existing real controller evidence is reused below. These are owner API "
        "audits, not acceptance based only on HTTP status. Evidence dates and hashes are retained.",
        "",
        "| Scenario / mode | Reconciled checks | Original completion UTC |",
        "|---|---:|---|",
    ]
    for key, (run, _) in sorted(failures.items()):
        rows.append(f"| {key} | {len(run['checks'])} | {run['completed_at']} |")
    if not refunds:
        rows += [
            "",
            "**Fresh refund rehearsal: NOT_RUN.** Preparation failed with catalogue "
            "HTTP 503 before a checkout was submitted. The existing debit/reversal "
            "unit/oracle tests are not substituted for a real refund demonstration.",
        ]
    rows += [
        "",
        "An uncertain checkout response is retried with the identical request/key/body, "
        "not a new purchase. A saga restores stock on cancellation. The ordinary 35-second "
        "late-payment case quiesces before debit; it is not evidence that a paid amount was "
        "refunded. A refund claim needs one real debit, exactly one matching reversal, "
        "cancelled order, restored stock and matching Gold.",
        "",
        "Analytics pause/catch-up verifies that checkout can complete independently, "
        "then reconciles the exact final order after recovery. Lag=0 alone is insufficient: "
        "pending Gold/outboxes and exact active membership are checked separately. This "
        "single-broker, single-host prototype does not demonstrate broker replication, "
        "host disaster recovery, Byzantine faults or a multi-host network partition.",
        "",
        "## Q13-Q14. Can we trust the metrics and the independent checker?",
        "",
        "Fresh tests cover hand-computed quantiles/lag/goodput, unfinished denominators, "
        "clock qualification, preservation of send identities, changed-control rejection, "
        "and deliberate oracle corruptions (duplicate debit, wrong money/state, missing "
        "events). Fault doubles are labelled; passing them proves a guard detects a case, "
        "not a real outage performance measurement. Unknown/missing timings stay null.",
        "",
        "| Probable question | Existing/new executable test coverage |",
        "|---|---|",
        "| What does a summary lose? What if seen IDs expire? | "
        "benchmarks.defense.summary_trials; tests/benchmarks/test_defense.py |",
        "| Why B-tree/hash/BRIN/GIN and which bottleneck? | "
        "benchmarks.defense.index_trials; raw EXPLAIN ANALYZE BUFFERS plans and "
        "update/WAL probe |",
        "| Are all repetitions and negative results retained? | test_defense.py; "
        "test_comparison.py; test_windows_measurements.py |",
        "| How are dirty/missing CSV values handled? | tests/catalog/test_normalize.py; "
        "original-source conservation in catalogue() |",
        "| Duplicate ID versus conflicting payload? | retained duplicate/conflict runs; "
        "test_journey.py; tests/pipelines/test_replay.py |",
        "| Out-of-order/late/replayed events? | retained real runs; test_journey.py; "
        "test_replay.py |",
        "| Can two shoppers buy the last unit? | retained race run plus independent "
        "saved-ledger checks in defense_report.edge_evidence |",
        "| Lost response, expiry, compensation or refund? | retained owner API audits; "
        "test_failure_demo.py; tests/oracles/test_reconciliation.py |",
        "| Why not report low lag as completion? | test_journey.py; test_performance_metrics.py |",
        "| Does the generator hide slow/unfinished requests? | test_scheduler.py; "
        "test_metrics.py |",
        "| Can the checker detect deliberately wrong answers? | "
        "tests/oracles/test_reconciliation.py; test_failure_demo.py; test_defense.py |",
        "| Does compaction delete history or switch a stale snapshot? | existing "
        "test_compaction_live.py/test_publication_live.py; no new Linux durability pass "
        "claimed here |",
        "",
        "## Commands, evidence and remaining limits",
        "",
        "```powershell",
        f".venv\\Scripts\\python.exe -m benchmarks.defense --out {rel}-new --samples 10",
        ".venv\\Scripts\\python.exe -m benchmarks.defense_report --run "
        + rel
        + " --junit "
        + junit.relative_to(ROOT).as_posix()
        + " --refund "
        + refund_dir.relative_to(ROOT).as_posix()
        + " --out docs/jaineel/PROFESSOR_QUESTIONS_AND_RESULTS.md",
        "```",
        "",
        "The first command requires Windows Desktop, the existing pinned image and a "
        "fresh output directory. It creates one labelled disposable PostgreSQL container "
        "and removes it plus anonymous volumes in finally; its actual removal is verified. "
        "No retained prototype database is reset. Raw timings/plans/Parquet stay local under "
        "artifacts; reports do not include credentials.",
        "",
        "A complete formal comparison still needs quiet fixed resources, the full "
        "workload matrix, complete resource/clock evidence and owner review gates. This "
        "report intentionally preserves the earlier failed benchmark status and the fresh "
        "refund attempt's dependency failure. It does not turn exploratory timings or "
        "correctness tests into a production capacity claim. The measurement/report commands "
        "do not run CI/CD or change Git history.",
    ]
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return report_data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--refund", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.run.resolve(), args.junit.resolve(), args.refund.resolve(), args.out)
    print(f"Defense report written: {args.out}; {result['pytest']['passed']} correctness passes")


if __name__ == "__main__":
    main()
