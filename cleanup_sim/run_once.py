from __future__ import annotations

import argparse
from pathlib import Path

from .config import PlannerMode, ScenarioName, scenario_config
from .io import save_result
from .plots import plot_single_result
from .simulation import run_simulation


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run one cleanup simulation.")
    p.add_argument("--scenario", choices=["clustered_base", "clustered_noisy", "uniform_base"], default="clustered_base")
    p.add_argument(
        "--mode",
        choices=[
            "lawnmower",
            "lawnmower_sparse",
            "lawnmower_dense",
            "greedy",
            "active",
            "detected_tsp",
            "graph_mst",
            "hybrid",
            "hybrid_mst",
        ],
        default="active",
    )
    p.add_argument("--seed", type=int, default=11)
    p.add_argument("--out-dir", type=Path, default=Path("out/cleanup_sim/single"))
    return p


def main() -> None:
    args = build_parser().parse_args()
    cfg = scenario_config(args.scenario, args.seed, args.mode)
    result = run_simulation(cfg)
    prefix = f"{args.scenario}__{args.mode}__seed{args.seed}"
    files = save_result(result, args.out_dir, prefix)
    plots = plot_single_result(result, args.out_dir, prefix)
    print("Summary:")
    for k, v in result.summary.items():
        print(f"  {k}: {v}")
    print("Saved:")
    for path in [*files.values(), *plots]:
        print(f"  {path}")


if __name__ == "__main__":
    main()
