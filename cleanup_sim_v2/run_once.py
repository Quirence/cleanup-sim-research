from __future__ import annotations

import argparse
from pathlib import Path

from .config import ParameterProfile, PlannerMode, ScenarioName, scenario_config
from .io import save_run
from .simulation import run_simulation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one cleanup_sim_v2 simulation.")
    parser.add_argument("--scenario", choices=["static_calm", "weak_drift", "strong_drift", "robot_disturbed"], default="weak_drift")
    parser.add_argument("--mode", choices=["coverage", "greedy", "active", "confirmed_route"], default="active")
    parser.add_argument("--profile", choices=["low", "nominal", "high"], default="nominal")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out-dir", type=Path, default=Path("out/cleanup_sim_v2/run_once"))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    cfg = scenario_config(
        args.scenario,  # type: ignore[arg-type]
        args.seed,
        args.mode,  # type: ignore[arg-type]
        args.profile,  # type: ignore[arg-type]
    )
    result = run_simulation(cfg)
    prefix = f"{args.scenario}__{args.mode}__{args.profile}__seed{args.seed}"
    paths = save_run(result, args.out_dir, prefix)
    print(result.summary)
    print(f"saved: {paths['summary']}")


if __name__ == "__main__":
    main()
