from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

import pandas as pd

from .config import ScenarioName, ensure_output_dir, scenario_config
from .io import save_result
from .sensitivity import (
    aggregate_sensitivity_summary,
    apply_sensitivity_case,
    cases_to_frame,
    iter_sensitivity_cases,
)
from .simulation import run_simulation


DEFAULT_SCENARIOS: list[ScenarioName] = ["clustered_base", "clustered_noisy", "uniform_base"]


def _write_tables(out_dir: Path, cases: list, summaries: list[dict]) -> None:
    summary_df = pd.DataFrame(summaries)
    summary_df.to_csv(out_dir / "summary_partial.csv", index=False)
    if not summary_df.empty:
        aggregate_df = aggregate_sensitivity_summary(summary_df)
        aggregate_df.to_csv(out_dir / "aggregate_partial.csv", index=False)
    cases_to_frame(cases).to_csv(out_dir / "sensitivity_cases.csv", index=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run OFAT sensitivity analysis for the hybrid planner.")
    parser.add_argument("--seeds", type=int, default=5, help="Number of seeds per scenario and sensitivity case.")
    parser.add_argument("--out-dir", type=Path, default=Path("out/cleanup_sim/sensitivity_ofat"))
    parser.add_argument("--scenarios", nargs="*", choices=DEFAULT_SCENARIOS, default=DEFAULT_SCENARIOS)
    parser.add_argument("--tmax-s", type=float, default=None, help="Optional simulation time limit override.")
    parser.add_argument("--max-path-m", type=float, default=6000.0, help="Optional path budget override.")
    parser.add_argument(
        "--components",
        nargs="*",
        choices=["planner", "robot"],
        default=None,
        help="Optional sensitivity components to run. Baseline is always included.",
    )
    parser.add_argument("--save-runs", action="store_true", help="Save per-run events, series, maps and configs.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    out_dir = ensure_output_dir(args.out_dir)
    run_dir = ensure_output_dir(out_dir / "runs") if args.save_runs else None

    baseline_planner = scenario_config("clustered_base", 0, "hybrid").planner
    cases = iter_sensitivity_cases(baseline_planner)
    if args.components is not None:
        wanted = set(args.components) | {"baseline"}
        cases = [case for case in cases if case.component in wanted]
    summaries = []
    _write_tables(out_dir, cases, summaries)

    for scenario in args.scenarios:
        for case in cases:
            for seed in range(args.seeds):
                cfg = scenario_config(scenario, seed, "hybrid")
                cfg = apply_sensitivity_case(cfg, case)
                if args.tmax_s is not None:
                    cfg = replace(cfg, robot=replace(cfg.robot, tmax_s=args.tmax_s))
                if args.max_path_m is not None:
                    cfg = replace(cfg, planner=replace(cfg.planner, max_path_m=args.max_path_m))
                result = run_simulation(cfg)
                summary = dict(result.summary)
                summary["sensitivity_case"] = case.name
                summary["sensitivity_component"] = case.component
                summary["sensitivity_parameter"] = case.parameter or "baseline"
                summary["sensitivity_value"] = case.value
                summaries.append(summary)

                if run_dir is not None:
                    prefix = f"{scenario}__{case.name.replace('=', '-')}__seed{seed}"
                    save_result(result, run_dir, prefix)
                _write_tables(out_dir, cases, summaries)
                print(
                    "done "
                    f"scenario={scenario} case={case.name} seed={seed} "
                    f"collected={summary['collected_ratio']:.3f} auc={summary['auc_collected_by_path']:.3f}"
                )

    summary_df = pd.DataFrame(summaries)
    aggregate_df = aggregate_sensitivity_summary(summary_df)
    cases_df = cases_to_frame(cases)

    summary_path = out_dir / "summary.csv"
    aggregate_path = out_dir / "aggregate_sensitivity.csv"
    cases_path = out_dir / "sensitivity_cases.csv"
    summary_df.to_csv(summary_path, index=False)
    aggregate_df.to_csv(aggregate_path, index=False)
    cases_df.to_csv(cases_path, index=False)
    (out_dir / "experiment_config.json").write_text(
        json.dumps(
            {
                "seeds": args.seeds,
                "scenarios": args.scenarios,
                "tmax_s": args.tmax_s,
                "max_path_m": args.max_path_m,
                "components": args.components,
                "save_runs": args.save_runs,
                "design": "one-factor-at-a-time around frozen hybrid_final_v1 planner",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"summary: {summary_path}")
    print(f"aggregate: {aggregate_path}")
    print(f"cases: {cases_path}")


if __name__ == "__main__":
    main()
