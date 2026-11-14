"""Rebuild diagnostic comparisons without promoting failed or incomplete evidence."""

import argparse
import json
from pathlib import Path

from benchmarks.windows.evidence import ROOT, desktop_only, digest, write
from benchmarks.windows.measure import summarize


def rebuild(run, out):
    manifest_path = run / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    journal = run / "measurements.jsonl"
    expected = manifest.get("files", {}).get("measurements.jsonl")
    if not expected or digest(journal) != expected:
        raise ValueError("Measurement journal does not match its original manifest hash")
    rows = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    if {r["axis"] for r in rows} != {"import", "index", "batch", "compaction"}:
        raise ValueError("All four measurement axes must be present")
    comparisons = summarize(rows, manifest["repetitions"])
    document = {
        "status": "DIAGNOSTIC_ONLY",
        "qualified_performance_claim": False,
        "source_status": manifest["status"],
        "source_manifest_sha256": digest(manifest_path),
        "source_journal_sha256": expected,
        "source_error_type": manifest.get("error_type"),
        "quick": manifest.get("quick", False),
        "repetitions": manifest["repetitions"],
        "measurement_rows": len(rows),
        "limitation": "Unqualified observations; all original run failures remain in force. "
        "These numbers cannot establish an optimization or a formal performance claim.",
        "comparisons": comparisons,
    }
    write(out / "diagnostic-comparison.json", document)
    lines = [
        "# Diagnostic observations — NOT QUALIFIED",
        "",
        document["limitation"],
        "",
        f"Original run: {manifest['status']}. Quick mode: {document['quick']}. "
        f"Paired repetitions: {manifest['repetitions']}. Raw observations: {len(rows)}.",
        "",
        "| Comparison | Baseline median s | Candidate median s | Observed change % |",
        "|---|---:|---:|---:|",
    ]
    for name, value in comparisons.items():
        change = value["improvement_percent"]
        lines.append(
            f"| {name} | {value['baseline']['median']:.6f} | "
            f"{value['candidate']['median']:.6f} | "
            + (f"{change:.2f}" if change is not None else "null")
            + " |"
        )
    (out / "diagnostic-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    desktop_only()
    run = args.run.resolve()
    if not run.is_relative_to(ROOT / "artifacts/windows"):
        parser.error("Choose a run under this Desktop checkout's artifacts/windows")
    out = ROOT / "artifacts/windows/reports" / run.name
    out.mkdir(parents=True, exist_ok=True)
    rebuild(run, out)
    print(f"Unqualified diagnostic observations: {out}")


if __name__ == "__main__":
    main()
