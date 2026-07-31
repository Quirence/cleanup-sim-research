from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

import pandas as pd

from .config import ScenarioName, ensure_output_dir
from .confirmatory import build_confirmatory_arms, config_for_arm
from .io import save_result
from .run_experiments import aggregate_summary
from .simulation import run_simulation
from .statistics import paired_comparison_table


DEFAULT_SCENARIOS: list[ScenarioName] = ["clustered_base", "clustered_noisy", "uniform_base"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run confirmatory comparison for hybrid candidate settings.")
    parser.add_argument("--seeds", type=int, default=5, help="Number of seeds per scenario and arm.")
    parser.add_argument("--out-dir", type=Path, default=Path("out/cleanup_sim/confirmatory_hybrid_v2"))
    parser.add_argument("--scenarios", nargs="*", choices=DEFAULT_SCENARIOS, default=DEFAULT_SCENARIOS)
    parser.add_argument("--tmax-s", type=float, default=12000.0, help="Simulation time limit override.")
    parser.add_argument("--max-path-m", type=float, default=6000.0, help="Path budget override.")
    parser.add_argument("--save-runs", action="store_true", help="Save per-run events, series, maps and configs.")
    return parser


def _write_tables(out_dir: Path, summaries: list[dict]) -> None:
    summary_df = pd.DataFrame(summaries)
    summary_df.to_csv(out_dir / "summary_partial.csv", index=False)
    if not summary_df.empty:
        aggregate_summary(summary_df).to_csv(out_dir / "aggregate_partial.csv", index=False)
        paired_comparison_table(summary_df, reference_mode="hybrid_candidate_v2").to_csv(
            out_dir / "paired_partial.csv",
            index=False,
        )


def main() -> None:
    args = build_parser().parse_args()
    out_dir = ensure_output_dir(args.out_dir)
    run_dir = ensure_output_dir(out_dir / "runs") if args.save_runs else None
    arms = build_confirmatory_arms()
    summaries: list[dict] = []
    _write_tables(out_dir, summaries)

    for scenario in args.scenarios:
        for arm in arms:
            for seed in range(args.seeds):
                cfg = config_for_arm(scenario, seed, arm)
                if args.tmax_s is not None:
                    cfg = replace(cfg, robot=replace(cfg.robot, tmax_s=args.tmax_s))
                if args.max_path_m is not None:
                    cfg = replace(cfg, planner=replace(cfg.planner, max_path_m=args.max_path_m))
                result = run_simulation(cfg)
                summary = dict(result.summary)
                summary["mode"] = arm.label
                summary["planner_mode_internal"] = cfg.planner.mode
                summary["hybrid_explore_entropy_threshold"] = cfg.planner.hybrid_explore_entropy_threshold
                summaries.append(summary)

                if run_dir is not None:
                    save_result(result, run_dir, f"{scenario}__{arm.label}__seed{seed}")
                _write_tables(out_dir, summaries)
                print(
                    "done "
                    f"scenario={scenario} arm={arm.label} seed={seed} "
                    f"collected={summary['collected_ratio']:.3f} auc={summary['auc_collected_by_path']:.3f}"
                )

    summary_df = pd.DataFrame(summaries)
    aggregate_df = aggregate_summary(summary_df)
    comparisons_df = paired_comparison_table(summary_df, reference_mode="hybrid_candidate_v2")
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
                "arms": [arm.__dict__ for arm in arms],
                "tmax_s": args.tmax_s,
                "max_path_m": args.max_path_m,
                "purpose": "confirm hybrid candidate-v2 before final 30-seed experiment",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"summary: {summary_path}")
    print(f"aggregate: {aggregate_path}")
    print(f"paired comparisons: {comparisons_path}")


if __name__ == "__main__":
    main()
