from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

import pandas as pd

from .config import scenario_config
from .io import config_hash, git_commit, git_dirty, save_run
from .simulation import run_simulation


DEFAULT_SCENARIOS = ["static_calm", "weak_drift", "strong_drift", "robot_disturbed"]
ALL_SCENARIOS = [
    "static_calm",
    "weak_drift",
    "strong_drift",
    "robot_disturbed",
    "uniform_static_calm",
    "uniform_weak_drift",
    "uniform_strong_drift",
    "uniform_robot_disturbed",
]
ALL_MODES = [
    "coverage",
    "lawnmower_survey",
    "lawnmower_collect",
    "greedy",
    "active",
    "belief_horizon",
    "belief_horizon_approach_aware",
    "belief_horizon_density_risk_gate",
    "belief_horizon_retarget",
    "belief_horizon_retarget_strict",
    "belief_horizon_retarget_locked",
    "belief_horizon_retarget_region",
    "belief_horizon_retarget_drift_switch",
    "belief_horizon_provisional",
    "belief_cluster_route",
    "belief_orienteering",
    "belief_orienteering_provisional",
    "belief_orienteering_depth1",
    "belief_orienteering_no_opportunity_cost",
    "belief_orienteering_density_disabled",
    "belief_horizon_no_efficiency",
    "belief_horizon_no_track_prediction",
    "belief_horizon_no_refinement",
    "confirmed_route",
    "oracle_perfect_static",
    "oracle_current_physics",
    "oracle_route_heuristic",
]
DEFAULT_MODES = ["lawnmower_survey", "lawnmower_collect", "greedy", "confirmed_route", "oracle_current_physics"]
BASELINE_MODES = ["lawnmower_survey", "lawnmower_collect", "greedy"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run cleanup_sim_v2 experiment series.")
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--scenarios", nargs="+", choices=ALL_SCENARIOS, default=DEFAULT_SCENARIOS)
    parser.add_argument("--modes", nargs="+", choices=ALL_MODES, default=DEFAULT_MODES)
    parser.add_argument("--profile", choices=["low", "nominal", "high"], default="nominal")
    parser.add_argument("--out-dir", type=Path, default=Path("out/cleanup_sim_v2/experiments"))
    parser.add_argument("--save-runs", action="store_true")
    parser.add_argument("--baseline-only", action="store_true")
    parser.add_argument("--max-path-m", type=float, default=None)
    parser.add_argument("--tmax-s", type=float, default=None)
    parser.add_argument("--checkpoint", action="store_true", help="Write partial CSV outputs after each run.")
    parser.add_argument("--resume", action="store_true", help="Resume from out-dir/summary_partial.csv when present.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    partial_summary_path = args.out_dir / "summary_partial.csv"
    partial_aggregate_path = args.out_dir / "aggregate_partial_mean_std.csv"
    summaries = []
    completed_keys: set[tuple[str, str, str, int]] = set()
    if args.resume and partial_summary_path.exists():
        partial_df = pd.read_csv(partial_summary_path)
        summaries = partial_df.to_dict("records")
        for row in summaries:
            completed_keys.add((str(row["scenario"]), str(row["profile"]), str(row["mode"]), int(row["seed"])))
    modes = BASELINE_MODES if args.baseline_only else args.modes
    commit = git_commit()
    dirty = git_dirty()
    for scenario in args.scenarios:
        for mode in modes:
            for seed in range(args.seeds):
                run_key = (scenario, args.profile, mode, seed)
                if run_key in completed_keys:
                    print(f"skip scenario={scenario} mode={mode} seed={seed} reason=resume")
                    continue
                cfg = scenario_config(scenario, seed, mode, args.profile)  # type: ignore[arg-type]
                if args.max_path_m is not None or args.tmax_s is not None:
                    cfg = replace(
                        cfg,
                        platform=replace(
                            cfg.platform,
                            max_path_m=cfg.platform.max_path_m if args.max_path_m is None else args.max_path_m,
                            tmax_s=cfg.platform.tmax_s if args.tmax_s is None else args.tmax_s,
                        ),
                    )
                result = run_simulation(cfg)
                cfg_hash = config_hash(cfg.to_dict())
                result.summary.update(
                    {
                        "config_hash": cfg_hash,
                        "git_commit": commit,
                        "git_dirty": dirty,
                        "runner": "run_experiments",
                    }
                )
                summaries.append(result.summary)
                if args.save_runs:
                    prefix = f"{scenario}__{mode}__{args.profile}__seed{seed}"
                    save_run(result, args.out_dir / "runs", prefix)
                if args.checkpoint:
                    partial_df = pd.DataFrame(summaries)
                    partial_df.to_csv(partial_summary_path, index=False)
                    numeric_cols = partial_df.select_dtypes(include="number").columns
                    if len(numeric_cols) > 0:
                        partial_df.groupby(["scenario", "profile", "mode"])[numeric_cols].agg(["mean", "std"]).to_csv(
                            partial_aggregate_path
                        )
                print(
                    f"done scenario={scenario} mode={mode} seed={seed} "
                    f"collected={result.summary['collected_ratio']:.3f} "
                    f"empty_goals={result.summary['empty_goal_arrivals']}"
                )
    df = pd.DataFrame(summaries)
    if "oracle_current_physics" in set(df["mode"]):
        keys = ["scenario", "profile", "seed"]
        oracle = df[df["mode"] == "oracle_current_physics"][
            keys + ["collected_ratio", "auc_collected_by_path", "path_length_m"]
        ].rename(
            columns={
                "collected_ratio": "oracle_current_collected_ratio",
                "auc_collected_by_path": "oracle_current_auc_collected_by_path",
                "path_length_m": "oracle_current_path_length_m",
            }
        )
        df = df.merge(oracle, on=keys, how="left")
        df["oracle_gap_collected_ratio"] = df["oracle_current_collected_ratio"] - df["collected_ratio"]
        df["oracle_gap_auc_collected_by_path"] = df["oracle_current_auc_collected_by_path"] - df["auc_collected_by_path"]
        df["collected_ratio_vs_oracle"] = df["collected_ratio"] / df["oracle_current_collected_ratio"].clip(lower=1e-9)
    summary_path = args.out_dir / "summary.csv"
    aggregate_path = args.out_dir / "aggregate_mean_std.csv"
    manifest_path = args.out_dir / "run_manifest.json"
    df.to_csv(summary_path, index=False)
    numeric_cols = df.select_dtypes(include="number").columns
    aggregate = df.groupby(["scenario", "profile", "mode"])[numeric_cols].agg(["mean", "std"])
    aggregate.to_csv(aggregate_path)
    manifest_path.write_text(
        json.dumps(
            {
                "runner": "cleanup_sim_v2.run_experiments",
                "git_commit": commit,
                "git_dirty": dirty,
                "seeds": args.seeds,
                "scenarios": args.scenarios,
                "modes": modes,
                "profile": args.profile,
                "max_path_m": args.max_path_m,
                "tmax_s": args.tmax_s,
                "save_runs": args.save_runs,
                "checkpoint": args.checkpoint,
                "resume": args.resume,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"summary: {summary_path}")
    print(f"aggregate: {aggregate_path}")
    print(f"manifest: {manifest_path}")


if __name__ == "__main__":
    main()
