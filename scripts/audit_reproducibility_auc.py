"""Reanalyse immutable control traces and verify that the AUC fix preserves physics."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from cleanup_sim_v2.metrics import auc_by_path
from cleanup_sim_v2.provenance import REPO_ROOT, file_sha256
from scripts.check_reproducibility import METADATA_FIELDS, write_json


def read_curve(path: Path) -> tuple[list[float], list[float]]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    return [float(row["path_m"]) for row in rows], [float(row["collected_ratio"]) for row in rows]


def legacy_auc(path_m: list[float], ratios: list[float], budget_m: float, kind: str) -> float:
    """Metric from d92b496, with sorting kind exposed only for diagnosis."""
    x, y = np.asarray(path_m), np.asarray(ratios)
    order = np.argsort(x, kind=kind)
    x, y = x[order], y[order]
    if x[0] > 0:
        x, y = np.insert(x, 0, 0.0), np.insert(y, 0, y[0])
    if x[-1] < budget_m:
        x, y = np.append(x, budget_m), np.append(y, y[-1])
    else:
        at_budget = np.interp(budget_m, x, y)
        keep = x < budget_m
        x, y = np.append(x[keep], budget_m), np.append(y[keep], at_budget)
    return float(np.trapezoid(y, x) / max(1e-9, budget_m))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-dir", type=Path, required=True)
    parser.add_argument("--followup-dir", type=Path, required=True)
    parser.add_argument("--out-file", type=Path, required=True)
    args = parser.parse_args()
    if args.out_file.exists():
        raise FileExistsError("Use a new audit output file; existing evidence is immutable.")
    rows = []
    for path in sorted((args.control_dir / "repeat1").glob("*_manifest.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        series_path = path.parent / manifest["artifacts"]["series"]["file"]
        x, y = read_curve(series_path)
        budget = manifest["config"]["platform"]["max_path_m"]
        rows.append({
            "mode": manifest["summary"]["mode"], "seed": manifest["summary"]["seed"],
            "series_sha256": file_sha256(series_path),
            "series_integrity_ok": file_sha256(series_path) == manifest["artifacts"]["series"]["sha256"],
            "duplicate_path_samples": len(x) - len(set(x)),
            "stationary_collection_increments": int(((np.diff(x) == 0) & (np.diff(y) > 0)).sum()),
            "recorded_auc": manifest["summary"]["auc_collected_by_path"],
            "legacy_quicksort_auc": legacy_auc(x, y, budget, "quicksort"),
            "legacy_stable_auc": legacy_auc(x, y, budget, "stable"),
            "legacy_heapsort_auc": legacy_auc(x, y, budget, "heapsort"),
            "corrected_auc": auc_by_path(x, y, budget),
        })
    cross_version = []
    for path in sorted(args.followup_dir.glob("repeat*/*_manifest.json")):
        after = json.loads(path.read_text(encoding="utf-8"))
        before_path = args.control_dir / "repeat1" / path.name
        before = json.loads(before_path.read_text(encoding="utf-8"))
        artifacts = {}
        for kind in ("config", "events", "series", "density", "positions"):
            old = before_path.parent / before["artifacts"][kind]["file"]
            new = path.parent / after["artifacts"][kind]["file"]
            artifacts[kind] = (
                file_sha256(old) == before["artifacts"][kind]["sha256"]
                == after["artifacts"][kind]["sha256"] == file_sha256(new)
            )
        fields = (before["summary"].keys() | after["summary"].keys()) - METADATA_FIELDS - {"auc_collected_by_path"}
        different_fields = [key for key in sorted(fields) if before["summary"].get(key) != after["summary"].get(key)]
        curve = read_curve(before_path.parent / before["artifacts"]["series"]["file"])
        expected_auc = auc_by_path(*curve, before["config"]["platform"]["max_path_m"])
        cross_version.append({
            "run": f"{path.parent.name}/{path.name}", "exact_artifacts": artifacts,
            "different_non_auc_fields": different_fields,
            "new_auc_matches_reanalysis_exactly": expected_auc == after["summary"]["auc_collected_by_path"],
        })
    valid = (
        len(rows) == 4 and len(cross_version) == 2
        and all(row["series_integrity_ok"] and row["recorded_auc"] == row["legacy_quicksort_auc"] for row in rows)
        and all(all(row["exact_artifacts"].values()) and not row["different_non_auc_fields"]
                and row["new_auc_matches_reanalysis_exactly"] for row in cross_version)
    )
    write_json(args.out_file, {
        "metric_source_sha256": file_sha256(REPO_ROOT / "cleanup_sim_v2/metrics.py"),
        "audit_source_sha256": file_sha256(Path(__file__)),
        "rows": rows, "cross_version": cross_version, "validation_passed": valid,
        "historical_cause_resolved": False,
        "interpretation": "tie ordering changes AUC on identical saved trajectories; does not explain seed 300 collection discrepancy",
    })
    print(f"validation_passed={valid}; audit={args.out_file}")
    if not valid:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
