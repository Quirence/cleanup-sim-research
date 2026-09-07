from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from cleanup_sim.statistics import paired_comparison_table

from .io import config_hash, git_commit, git_dirty, save_run
from .layer1 import (
    LAYER1_BUDGETS_M,
    LAYER1_MODES,
    LAYER1_SCENARIOS,
    adaptive_policy_shares,
    enrich_summary,
    evaluate_budget_calibration,
    layer1_config,
    regime_metrics_for_config,
    select_nominal_budget,
    safety_tmax_s,
    write_json,
)
from .layer1_validation import ExpectedMatrix, has_failing_issues, validate_summary, write_validation_outputs
from .simulation import run_simulation
from .provenance import (
    assert_provenance_unchanged, capture_provenance, summary_provenance,
    validate_resume_configs, validate_resume_provenance,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run layer-1 path-budget calibration and baseline experiments.")
    parser.add_argument("--phase", choices=["calibration", "baseline", "trace", "all"], default="calibration")
    parser.add_argument("--budgets", nargs="+", type=float, default=list(LAYER1_BUDGETS_M))
    parser.add_argument("--budget", type=float, default=None, help="Nominal budget for baseline/trace phases.")
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--seed-start", type=int, default=30)
    parser.add_argument("--scenarios", nargs="+", default=list(LAYER1_SCENARIOS))
    parser.add_argument("--modes", nargs="+", default=list(LAYER1_MODES))
    parser.add_argument("--profile", choices=["low", "nominal", "high"], default="nominal")
    parser.add_argument("--out-root", type=Path, default=Path("out/cleanup_sim_v2"))
    parser.add_argument("--calibration-out-dir", type=Path, default=None)
    parser.add_argument("--baseline-out-dir", type=Path, default=None)
    parser.add_argument("--trace-out-dir", type=Path, default=None)
    parser.add_argument("--checkpoint", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--save-runs", action="store_true", help="Save detailed run artifacts for every executed run.")
    parser.add_argument("--skip-validation", action="store_true", help="Do not validate the final summary.")
    parser.add_argument("--fail-on", choices=["blocker", "major", "warning"], default="major")
    return parser


def _default_calibration_dir(out_root: Path) -> Path:
    return out_root / "layer1_postfix_budget_calibration_2026-08-22"


def _default_baseline_dir(out_root: Path) -> Path:
    return out_root / "layer1_postfix_path_budget_baseline_2026-08-22"


def _default_trace_dir(out_root: Path) -> Path:
    return out_root / "layer1_postfix_adaptive_trace_2026-08-22"


def _completed_keys(summary: list[dict]) -> set[tuple[float, str, str, str, int]]:
    keys: set[tuple[float, str, str, str, int]] = set()
    for row in summary:
        keys.add(
            (
                float(row["path_budget_m"]),
                str(row["scenario"]),
                str(row["profile"]),
                str(row["mode"]),
                int(row["seed"]),
            )
        )
    return keys


def _add_oracle_gaps(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "oracle_current_physics" not in set(df["mode"]):
        return df
    keys = ["path_budget_m", "scenario", "profile", "seed"]
    oracle = df[df["mode"] == "oracle_current_physics"][
        keys + ["collected_ratio", "auc_collected_by_path", "path_length_m"]
    ].rename(
        columns={
            "collected_ratio": "oracle_current_collected_ratio",
            "auc_collected_by_path": "oracle_current_auc_collected_by_path",
            "path_length_m": "oracle_current_path_length_m",
        }
    )
    merged = df.merge(oracle, on=keys, how="left")
    merged["oracle_gap_collected_ratio"] = merged["oracle_current_collected_ratio"] - merged["collected_ratio"]
    merged["oracle_gap_auc_collected_by_path"] = (
        merged["oracle_current_auc_collected_by_path"] - merged["auc_collected_by_path"]
    )
    merged["collected_ratio_vs_oracle"] = (
        merged["collected_ratio"] / merged["oracle_current_collected_ratio"].clip(lower=1e-9)
    )
    return merged


def _write_summary_outputs(df: pd.DataFrame, out_dir: Path, *, checkpoint: bool = False) -> pd.DataFrame:
    raw_path = out_dir / ("summary_partial.csv" if checkpoint else "summary.csv")
    enriched_path = out_dir / ("summary_enriched_partial.csv" if checkpoint else "summary_enriched.csv")
    aggregate_path = out_dir / ("aggregate_partial_mean_std.csv" if checkpoint else "aggregate_mean_std.csv")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(raw_path, index=False)
    enriched = enrich_summary(_add_oracle_gaps(df))
    enriched.to_csv(enriched_path, index=False)
    numeric_cols = enriched.select_dtypes(include="number").columns
    if len(numeric_cols) > 0:
        enriched.groupby(["path_budget_m", "scenario", "profile", "mode"])[numeric_cols].agg(["mean", "std"]).to_csv(
            aggregate_path
        )
    return enriched


def _write_paired_comparisons(enriched: pd.DataFrame, out_dir: Path) -> None:
    if enriched.empty or "adaptive_mission" not in set(enriched["mode"]):
        return
    rows: list[pd.DataFrame] = []
    for budget, bdf in enriched.groupby("path_budget_m", sort=True):
        metrics = tuple(
            metric
            for metric in (
                "auc_collected_by_path",
                "collected_ratio",
                "oracle_gap_auc_collected_by_path",
                "empty_goal_arrivals_per_km",
                "wasted_path_ratio",
                "goal_success_rate",
                "regret_to_best_fixed_auc",
            )
            if metric in bdf.columns
        )
        table = paired_comparison_table(bdf, reference_mode="adaptive_mission", metrics=metrics)
        if not table.empty:
            table.insert(0, "path_budget_m", float(budget))
            rows.append(table)
    if rows:
        pd.concat(rows, ignore_index=True).to_csv(out_dir / "paired_comparisons_by_budget.csv", index=False)


def run_series(
    *,
    phase: str,
    out_dir: Path,
    budgets: list[float],
    seeds: int,
    seed_start: int,
    scenarios: list[str],
    modes: list[str],
    profile: str,
    save_runs: bool,
    checkpoint: bool,
    resume: bool,
    validate_outputs: bool,
    fail_on: str,
) -> pd.DataFrame:
    out_dir.mkdir(parents=True, exist_ok=True)
    partial_path = out_dir / "summary_partial.csv"
    summaries: list[dict] = []
    if resume and partial_path.exists():
        summaries = pd.read_csv(partial_path).to_dict("records")
    completed = _completed_keys(summaries)
    provenance = capture_provenance()
    validate_resume_provenance(summaries, provenance)
    expected = {
        (float(budget), scenario, profile, mode, seed): config_hash(
            layer1_config(scenario, seed, mode, budget, profile).to_dict()
        )
        for budget in budgets for scenario in scenarios for mode in modes
        for seed in range(seed_start, seed_start + seeds)
    }
    validate_resume_configs(summaries, expected, ("path_budget_m", "scenario", "profile", "mode", "seed"))
    commit = git_commit()
    dirty = git_dirty()
    for budget in budgets:
        for scenario in scenarios:
            for mode in modes:
                for seed in range(seed_start, seed_start + seeds):
                    key = (float(budget), scenario, profile, mode, seed)
                    cfg = layer1_config(scenario, seed, mode, budget, profile)
                    cfg_hash = config_hash(cfg.to_dict())
                    if key in completed:
                        print(f"skip phase={phase} budget={budget:g} scenario={scenario} mode={mode} seed={seed}")
                        continue
                    result = run_simulation(cfg)
                    result.summary.update(
                        {
                            "phase": phase,
                            "path_budget_m": float(budget),
                            "safety_tmax_s": float(cfg.platform.tmax_s),
                            **regime_metrics_for_config(cfg, budget),
                            "config_hash": cfg_hash,
                            "git_commit": commit,
                            "git_dirty": dirty,
                            "runner": "run_layer1",
                            **summary_provenance(provenance),
                        }
                    )
                    summaries.append(result.summary)
                    if save_runs:
                        prefix = f"{scenario}__{mode}__{profile}__budget{int(budget)}__seed{seed}"
                        save_run(result, out_dir / "runs", prefix, provenance=provenance)
                    if checkpoint:
                        _write_summary_outputs(pd.DataFrame(summaries), out_dir, checkpoint=True)
                    print(
                        f"done phase={phase} budget={budget:g} scenario={scenario} mode={mode} seed={seed} "
                        f"collected={result.summary['collected_ratio']:.3f} stop={result.summary['stop_reason']}"
                    )
    df = pd.DataFrame(summaries)
    enriched = _write_summary_outputs(df, out_dir, checkpoint=False)
    _write_paired_comparisons(enriched, out_dir)
    write_json(
        out_dir / "run_manifest.json",
        {
            "runner": "cleanup_sim_v2.run_layer1",
            "phase": phase,
            "git_commit": commit,
            "git_dirty": dirty,
            "provenance": provenance,
            "budgets": budgets,
            "seeds": seeds,
            "seed_start": seed_start,
            "scenarios": scenarios,
            "modes": modes,
            "profile": profile,
            "save_runs": save_runs,
            "checkpoint": checkpoint,
            "resume": resume,
            "validation": validate_outputs,
            "fail_on": fail_on,
            "standard_budget_tmax_s": {str(b): safety_tmax_s(b) for b in LAYER1_BUDGETS_M},
        },
    )
    if validate_outputs:
        expected = ExpectedMatrix(
            budgets=tuple(float(budget) for budget in budgets),
            scenarios=tuple(str(scenario) for scenario in scenarios),
            modes=tuple(str(mode) for mode in modes),
            profile=str(profile),
            seed_start=int(seed_start),
            seeds=int(seeds),
        )
        issues = validate_summary(enriched, expected=expected)
        write_validation_outputs(out_dir, issues)
        if has_failing_issues(issues, fail_on):
            raise SystemExit(f"Layer-1 validation failed; inspect {out_dir / 'validation_issues.csv'}")
    print(f"summary: {out_dir / 'summary.csv'}")
    print(f"summary enriched: {out_dir / 'summary_enriched.csv'}")
    print(f"aggregate: {out_dir / 'aggregate_mean_std.csv'}")
    assert_provenance_unchanged(provenance)
    return enriched


def run_calibration(args: argparse.Namespace) -> tuple[pd.DataFrame, float | None]:
    out_dir = args.calibration_out_dir or _default_calibration_dir(args.out_root)
    enriched = run_series(
        phase="calibration",
        out_dir=out_dir,
        budgets=list(args.budgets),
        seeds=args.seeds,
        seed_start=args.seed_start,
        scenarios=list(args.scenarios),
        modes=list(args.modes),
        profile=args.profile,
        save_runs=args.save_runs,
        checkpoint=args.checkpoint,
        resume=args.resume,
        validate_outputs=not args.skip_validation,
        fail_on=args.fail_on,
    )
    calibration = evaluate_budget_calibration(enriched)
    calibration.to_csv(out_dir / "budget_calibration_decision.csv", index=False)
    selected = select_nominal_budget(calibration)
    write_json(out_dir / "budget_decision.json", {"selected_nominal_budget_m": selected})
    print(f"budget calibration: {out_dir / 'budget_calibration_decision.csv'}")
    print(f"selected nominal budget: {selected}")
    return calibration, selected


def run_baseline(args: argparse.Namespace, budget: float) -> pd.DataFrame:
    out_dir = args.baseline_out_dir or _default_baseline_dir(args.out_root)
    return run_series(
        phase="baseline",
        out_dir=out_dir,
        budgets=[budget],
        seeds=args.seeds,
        seed_start=args.seed_start,
        scenarios=list(args.scenarios),
        modes=list(args.modes),
        profile=args.profile,
        save_runs=args.save_runs,
        checkpoint=args.checkpoint,
        resume=args.resume,
        validate_outputs=not args.skip_validation,
        fail_on=args.fail_on,
    )


def run_trace(args: argparse.Namespace, budget: float) -> pd.DataFrame:
    out_dir = args.trace_out_dir or _default_trace_dir(args.out_root)
    enriched = run_series(
        phase="trace",
        out_dir=out_dir,
        budgets=[budget],
        seeds=args.seeds,
        seed_start=args.seed_start,
        scenarios=list(args.scenarios),
        modes=["adaptive_mission"],
        profile=args.profile,
        save_runs=True,
        checkpoint=args.checkpoint,
        resume=args.resume,
        validate_outputs=not args.skip_validation,
        fail_on=args.fail_on,
    )
    shares = adaptive_policy_shares([out_dir / "runs"])
    shares.to_csv(out_dir / "adaptive_policy_shares.csv", index=False)
    print(f"adaptive policy shares: {out_dir / 'adaptive_policy_shares.csv'}")
    return enriched


def main() -> None:
    args = build_parser().parse_args()
    if args.phase == "calibration":
        run_calibration(args)
        return
    if args.phase == "baseline":
        if args.budget is None:
            raise SystemExit("--budget is required for --phase baseline")
        run_baseline(args, args.budget)
        return
    if args.phase == "trace":
        if args.budget is None:
            raise SystemExit("--budget is required for --phase trace")
        run_trace(args, args.budget)
        return

    calibration, selected = run_calibration(args)
    budget = args.budget if args.budget is not None else selected
    if budget is None:
        raise SystemExit("No budget passed the calibration gate; inspect budget_calibration_decision.csv")
    baseline_args = argparse.Namespace(**{**vars(args), "seeds": 30, "seed_start": 40})
    run_baseline(baseline_args, float(budget))
    trace_args = argparse.Namespace(**{**vars(args), "seeds": 5, "seed_start": 40})
    run_trace(trace_args, float(budget))
    print(json.dumps({"selected_nominal_budget_m": budget, "calibration_rows": len(calibration)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
