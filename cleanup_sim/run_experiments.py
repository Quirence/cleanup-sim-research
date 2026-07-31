from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

import pandas as pd

from .config import PlannerMode, ScenarioName, ensure_output_dir, scenario_config
from .io import save_result
from .plots import plot_experiment_curves, plot_single_result
from .simulation import run_simulation
from .statistics import paired_comparison_table


DEFAULT_SCENARIOS: list[ScenarioName] = ["clustered_base", "clustered_noisy", "uniform_base"]
MODE_CHOICES: list[PlannerMode] = [
    "lawnmower",
    "lawnmower_sparse",
    "lawnmower_dense",
    "greedy",
    "active_entropy",
    "active_probability",
    "active_no_distance",
    "active",
    "detected_tsp",
    "hybrid",
]
DEFAULT_MODES: list[PlannerMode] = [
    "lawnmower_sparse",
    "lawnmower_dense",
    "greedy",
    "active_entropy",
    "active_probability",
    "active_no_distance",
    "active",
    "detected_tsp",
    "hybrid",
]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run cleanup simulation experiment series.")
    p.add_argument("--seeds", type=int, default=30, help="Number of seeds per scenario and mode.")
    p.add_argument("--out-dir", type=Path, default=Path("out/cleanup_sim/experiments"))
    p.add_argument("--scenarios", nargs="*", choices=DEFAULT_SCENARIOS, default=DEFAULT_SCENARIOS)
    p.add_argument("--modes", nargs="*", choices=MODE_CHOICES, default=DEFAULT_MODES)
    p.add_argument("--plot-examples", action="store_true", help="Save single-run plots for seed 0 of every scenario/mode.")
    p.add_argument("--tmax-s", type=float, default=None, help="Optional simulation time limit override for smoke runs.")
    p.add_argument("--max-path-m", type=float, default=None, help="Optional path budget override for smoke runs.")
    return p


def aggregate_summary(summary: pd.DataFrame) -> pd.DataFrame:
    metric_cols = [
        "collected_ratio",
        "mass_ratio",
        "path_length_m",
        "sim_time_s",
        "false_visits",
        "unload_events",
        "target_confirmed",
        "target_route_attempts",
        "target_visit_successes",
        "target_visit_false",
        "target_precision",
        "time_to_50_s",
        "time_to_80_s",
        "time_to_95_s",
        "path_to_50_m",
        "path_to_80_m",
        "path_to_95_m",
        "map_f1",
        "map_iou",
        "brier_score",
        "initial_map_f1",
        "initial_map_iou",
        "initial_brier_score",
        "initial_occupied_cells",
        "initial_multi_debris_cells",
        "initial_max_cell_count",
        "initial_mean_count_per_occupied_cell",
        "initial_occupancy_collision_ratio",
        "residual_map_f1",
        "residual_map_iou",
        "residual_brier_score",
        "residual_occupied_cells",
        "residual_multi_debris_cells",
        "residual_max_cell_count",
        "residual_mean_count_per_occupied_cell",
        "residual_occupancy_collision_ratio",
        "final_entropy",
        "auc_collected_by_path",
        "collected_ratio_at_2km",
        "collected_ratio_at_4km",
        "collected_ratio_at_6km",
        "collected_ratio_at_8km",
        "collected_ratio_at_10km",
        "collected_ratio_at_12km",
    ]
    threshold_cols = {
        "time_to_50_s",
        "time_to_80_s",
        "time_to_95_s",
        "path_to_50_m",
        "path_to_80_m",
        "path_to_95_m",
    }
    rows = []
    for (scenario, mode), group in summary.groupby(["scenario", "mode"]):
        row = {"scenario": scenario, "mode": mode, "runs": int(len(group))}
        for col in metric_cols:
            if col in group:
                row[f"{col}_mean"] = float(group[col].mean(skipna=True))
                row[f"{col}_std"] = float(group[col].std(skipna=True))
                if col in threshold_cols:
                    row[f"{col}_reach_rate"] = float(group[col].notna().mean())
                    row[f"{col}_reached"] = int(group[col].notna().sum())
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["scenario", "mode"]).reset_index(drop=True)


def main() -> None:
    args = build_parser().parse_args()
    out_dir = ensure_output_dir(args.out_dir)
    single_dir = ensure_output_dir(out_dir / "runs")
    plot_dir = ensure_output_dir(out_dir / "figures")
    summaries = []

    for scenario in args.scenarios:
        for mode in args.modes:
            for seed in range(args.seeds):
                cfg = scenario_config(scenario, seed, mode)
                if args.tmax_s is not None:
                    cfg = replace(cfg, robot=replace(cfg.robot, tmax_s=args.tmax_s))
                if args.max_path_m is not None:
                    cfg = replace(cfg, planner=replace(cfg.planner, max_path_m=args.max_path_m))
                result = run_simulation(cfg)
                prefix = f"{scenario}__{mode}__seed{seed}"
                save_result(result, single_dir, prefix)
                if args.plot_examples and seed == 0:
                    plot_single_result(result, plot_dir, prefix)
                summaries.append(result.summary)
                print(f"done scenario={scenario} mode={mode} seed={seed} collected={result.summary['collected_ratio']:.3f}")

    summary_df = pd.DataFrame(summaries)
    aggregate_df = aggregate_summary(summary_df)
    comparisons_df = paired_comparison_table(summary_df) if "hybrid" in set(summary_df["mode"]) else pd.DataFrame()
    summary_path = out_dir / "summary.csv"
    aggregate_path = out_dir / "aggregate_mean_std.csv"
    comparisons_path = out_dir / "paired_comparisons.csv"
    summary_df.to_csv(summary_path, index=False)
    aggregate_df.to_csv(aggregate_path, index=False)
    comparisons_df.to_csv(comparisons_path, index=False)
    (out_dir / "experiment_config.json").write_text(
        json.dumps(
            {
                "seeds": args.seeds,
                "scenarios": args.scenarios,
                "modes": args.modes,
                "tmax_s": args.tmax_s,
                "max_path_m": args.max_path_m,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    plot_experiment_curves(single_dir, plot_dir)
    print(f"summary: {summary_path}")
    print(f"aggregate: {aggregate_path}")
    print(f"paired comparisons: {comparisons_path}")
    print(f"figures: {plot_dir}")


if __name__ == "__main__":
    main()
