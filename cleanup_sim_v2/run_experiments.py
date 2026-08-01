from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .config import scenario_config
from .io import save_run
from .simulation import run_simulation


DEFAULT_SCENARIOS = ["static_calm", "weak_drift", "strong_drift", "robot_disturbed"]
DEFAULT_MODES = ["coverage", "greedy", "active", "confirmed_route"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run cleanup_sim_v2 experiment series.")
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--scenarios", nargs="+", choices=DEFAULT_SCENARIOS, default=DEFAULT_SCENARIOS)
    parser.add_argument("--modes", nargs="+", choices=DEFAULT_MODES, default=DEFAULT_MODES)
    parser.add_argument("--profile", choices=["low", "nominal", "high"], default="nominal")
    parser.add_argument("--out-dir", type=Path, default=Path("out/cleanup_sim_v2/experiments"))
    parser.add_argument("--save-runs", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    for scenario in args.scenarios:
        for mode in args.modes:
            for seed in range(args.seeds):
                cfg = scenario_config(scenario, seed, mode, args.profile)  # type: ignore[arg-type]
                result = run_simulation(cfg)
                summaries.append(result.summary)
                if args.save_runs:
                    prefix = f"{scenario}__{mode}__{args.profile}__seed{seed}"
                    save_run(result, args.out_dir / "runs", prefix)
                print(
                    f"done scenario={scenario} mode={mode} seed={seed} "
                    f"collected={result.summary['collected_ratio']:.3f} "
                    f"empty_goals={result.summary['empty_goal_arrivals']}"
                )
    df = pd.DataFrame(summaries)
    summary_path = args.out_dir / "summary.csv"
    aggregate_path = args.out_dir / "aggregate_mean_std.csv"
    df.to_csv(summary_path, index=False)
    numeric_cols = df.select_dtypes(include="number").columns
    aggregate = df.groupby(["scenario", "profile", "mode"])[numeric_cols].agg(["mean", "std"])
    aggregate.to_csv(aggregate_path)
    print(f"summary: {summary_path}")
    print(f"aggregate: {aggregate_path}")


if __name__ == "__main__":
    main()
