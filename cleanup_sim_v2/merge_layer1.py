from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .layer1 import (
    LAYER1_BUDGETS_M,
    LAYER1_MODES,
    LAYER1_SCENARIOS,
    adaptive_policy_shares,
    enrich_summary,
    evaluate_budget_calibration,
    select_nominal_budget,
    write_json,
)
from .layer1_validation import ExpectedMatrix, has_failing_issues, validate_summary, write_validation_outputs
from .run_layer1 import _add_oracle_gaps, _write_paired_comparisons


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Merge distributed layer-1 run chunks and validate the combined summary.")
    parser.add_argument("inputs", nargs="+", type=Path, help="Chunk directories or summary CSV files.")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--use-partial", action="store_true", help="Use summary_partial.csv when summary.csv is absent.")
    parser.add_argument("--budgets", nargs="+", type=float, default=list(LAYER1_BUDGETS_M))
    parser.add_argument("--scenarios", nargs="+", default=list(LAYER1_SCENARIOS))
    parser.add_argument("--modes", nargs="+", default=list(LAYER1_MODES))
    parser.add_argument("--profile", default="nominal")
    parser.add_argument("--seed-start", type=int, required=True)
    parser.add_argument("--seeds", type=int, required=True)
    parser.add_argument("--phase", default="calibration")
    parser.add_argument("--fail-on", choices=["blocker", "major", "warning"], default="major")
    parser.add_argument("--save-policy-shares", action="store_true")
    return parser


def _summary_path(path: Path, use_partial: bool) -> Path:
    if path.is_file():
        return path
    summary = path / "summary.csv"
    if summary.exists():
        return summary
    partial = path / "summary_partial.csv"
    if use_partial and partial.exists():
        return partial
    raise FileNotFoundError(f"No summary.csv found for {path}")


def read_summaries(inputs: list[Path], *, use_partial: bool) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for input_path in inputs:
        path = _summary_path(input_path, use_partial)
        df = pd.read_csv(path)
        df["source_summary_path"] = str(path)
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def write_merged_outputs(raw: pd.DataFrame, out_dir: Path, phase: str) -> pd.DataFrame:
    out_dir.mkdir(parents=True, exist_ok=True)
    raw.to_csv(out_dir / "summary.csv", index=False)
    enriched = enrich_summary(_add_oracle_gaps(raw))
    enriched.to_csv(out_dir / "summary_enriched.csv", index=False)
    numeric_cols = enriched.select_dtypes(include="number").columns
    if len(numeric_cols) > 0:
        enriched.groupby(["path_budget_m", "scenario", "profile", "mode"])[numeric_cols].agg(["mean", "std"]).to_csv(
            out_dir / "aggregate_mean_std.csv"
        )
    _write_paired_comparisons(enriched, out_dir)
    if phase == "calibration":
        calibration = evaluate_budget_calibration(enriched)
        calibration.to_csv(out_dir / "budget_calibration_decision.csv", index=False)
        write_json(out_dir / "budget_decision.json", {"selected_nominal_budget_m": select_nominal_budget(calibration)})
    return enriched


def main() -> None:
    args = build_parser().parse_args()
    raw = read_summaries(args.inputs, use_partial=args.use_partial)
    enriched = write_merged_outputs(raw, args.out_dir, args.phase)
    expected = ExpectedMatrix(
        budgets=tuple(float(budget) for budget in args.budgets),
        scenarios=tuple(str(scenario) for scenario in args.scenarios),
        modes=tuple(str(mode) for mode in args.modes),
        profile=str(args.profile),
        seed_start=int(args.seed_start),
        seeds=int(args.seeds),
    )
    issues = validate_summary(enriched, expected=expected)
    write_validation_outputs(args.out_dir, issues)
    if args.save_policy_shares:
        shares = adaptive_policy_shares([path / "runs" for path in args.inputs if path.is_dir()])
        shares.to_csv(args.out_dir / "adaptive_policy_shares.csv", index=False)
    manifest = {
        "runner": "cleanup_sim_v2.merge_layer1",
        "phase": args.phase,
        "inputs": [str(path) for path in args.inputs],
        "rows": int(len(raw)),
        "expected_rows": int(expected.expected_count),
        "issue_count": int(len(issues)),
        "fail_on": args.fail_on,
    }
    (args.out_dir / "merge_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    if has_failing_issues(issues, args.fail_on):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
