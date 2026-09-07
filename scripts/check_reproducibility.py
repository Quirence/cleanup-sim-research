"""Run the bounded September reproducibility protocol in separate processes."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import subprocess
import sys

from cleanup_sim_v2.provenance import REPO_ROOT, assert_provenance_unchanged, capture_provenance, file_sha256
from cleanup_sim_v2.reproducibility import compare_run_manifests


PROTOCOL = REPO_ROOT / "docs/project/reproducibility_control_protocol_2026-09-07.json"
REFERENCE_ROOT = REPO_ROOT / "out/cleanup_sim_v2"
REFERENCES = {
    "adaptive_mission": REFERENCE_ROOT / "colleague_adaptive_trace_3000_AFTERFIX_2026-08-29/layer1_postfix_adaptive_trace_2026-08-22",
    "belief_horizon": REFERENCE_ROOT / "colleague_baseline_3000_5seed_2026-08-29/layer1_postfix_path_budget_baseline_2026-08-22",
}
METADATA_FIELDS = {
    "runner", "git_commit", "git_dirty", "git_commit_full", "provenance_id",
    "source_sha256", "environment_sha256", "config_hash",
}


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def reference_comparison(summary: dict, directory: Path) -> dict:
    path = directory / "summary.csv"
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    rows = [row for row in rows if all(str(row[key]) == str(summary[key]) for key in ("scenario", "mode", "profile", "seed"))]
    if len(rows) != 1:
        raise ValueError(f"Expected exactly one reference row, got {len(rows)}: {path}")
    row = rows[0]
    differences = {}
    missing_fields = []
    for key, current in summary.items():
        if key in METADATA_FIELDS:
            continue
        if key not in row:
            missing_fields.append(key)
            continue
        original = row[key]
        if isinstance(current, (float, int)):
            equal = math.isclose(float(original), current, rel_tol=1e-12, abs_tol=1e-12)
        else:
            equal = original == str(current)
        if not equal:
            differences[key] = {"original": original, "current": current}
    return {
        "source": path.relative_to(REPO_ROOT).as_posix(), "source_sha256": file_sha256(path),
        "same_config_hash": row["config_hash"] == summary["config_hash"],
        "original_config_hash": row["config_hash"], "current_config_hash": summary["config_hash"],
        "original_git_commit": row["git_commit"], "original_git_dirty": row["git_dirty"],
        "original_events_available": False,
        "missing_summary_fields": missing_fields, "different_fields": differences,
        "reference_metrics": {key: row[key] for key in ("collected", "auc_collected_by_path", "sim_time_s", "stop_reason")},
        "current_metrics": {key: summary[key] for key in ("collected", "auc_collected_by_path", "sim_time_s", "stop_reason")},
        "status": "historical_diagnostic_only",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=PROTOCOL)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    if protocol["repeats"] != 2:
        raise ValueError("This pair comparator requires exactly two repeats.")
    provenance = capture_provenance()
    if provenance["git_dirty"] or provenance["git_commit_full"] == "unknown":
        raise SystemExit("Control requires a clean committed source tree, including the protocol.")
    # Refuse an existing directory, even if empty: no old CSV/trace is overwritten.
    args.out_dir.mkdir(parents=True, exist_ok=False)
    source_paths = [directory / name for directory in REFERENCES.values() for name in ("summary.csv", "run_manifest.json")]
    input_hashes = {path.relative_to(REPO_ROOT).as_posix(): file_sha256(path) for path in source_paths}
    write_json(args.out_dir / "protocol.json", protocol)
    write_json(args.out_dir / "provenance.json", provenance)
    write_json(args.out_dir / "input_hashes.json", input_hashes)
    pairs = []
    for mode in protocol["modes"]:
        for seed in protocol["seeds"]:
            prefix = f"{protocol['scenario']}__{mode}__{protocol['profile']}__seed{seed}"
            manifests = []
            for repeat in range(protocol["repeats"]):
                output = args.out_dir / f"repeat{repeat + 1}"
                output.mkdir(exist_ok=True)
                command = [
                    sys.executable, "-m", "cleanup_sim_v2.run_once",
                    "--scenario", protocol["scenario"], "--mode", mode,
                    "--profile", protocol["profile"], "--seed", str(seed),
                    "--max-path-m", str(protocol["max_path_m"]),
                    "--tmax-s", str(protocol["tmax_s"]), "--out-dir", str(output.resolve()),
                ]
                with (output / f"{prefix}_process.log").open("w", encoding="utf-8") as log:
                    subprocess.run(command, cwd=REPO_ROOT, check=True, stdout=log, stderr=subprocess.STDOUT, timeout=900)
                manifest = output / f"{prefix}_manifest.json"
                captured = json.loads(manifest.read_text(encoding="utf-8"))
                if captured["provenance"]["provenance_id"] != provenance["provenance_id"]:
                    raise RuntimeError("Child process identity differs from the protocol runner.")
                manifests.append(manifest)
                print(f"completed {mode} seed={seed} repeat={repeat + 1}", flush=True)
            comparison = compare_run_manifests(*manifests)
            summary = json.loads(manifests[0].read_text(encoding="utf-8"))["summary"]
            pairs.append({"mode": mode, "seed": seed, "repeat_comparison": comparison,
                          "historical_comparison": reference_comparison(summary, REFERENCES[mode])})
            write_json(args.out_dir / "comparisons_partial.json", pairs)
    assert_provenance_unchanged(provenance)
    originals_unchanged = all(file_sha256(REPO_ROOT / path) == digest for path, digest in input_hashes.items())
    passed = originals_unchanged and all(pair["repeat_comparison"]["passed"] for pair in pairs)
    report = {
        "protocol_sha256": file_sha256(args.protocol), "provenance_id": provenance["provenance_id"],
        "git_commit_full": provenance["git_commit_full"], "input_hashes": input_hashes,
        "originals_unchanged": originals_unchanged, "pairs": pairs,
        "current_repeatability_passed": passed, "historical_cause_resolved": False,
        "final_confirmatory_ready": False,
    }
    write_json(args.out_dir / "report.json", report)
    print(f"current_repeatability_passed={passed}; report={args.out_dir / 'report.json'}", flush=True)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
