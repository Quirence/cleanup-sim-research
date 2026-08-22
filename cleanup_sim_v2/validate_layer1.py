from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .layer1 import LAYER1_BUDGETS_M, LAYER1_MODES, LAYER1_SCENARIOS
from .layer1_validation import (
    ExpectedMatrix,
    has_failing_issues,
    issues_to_frame,
    validate_summary,
    validation_summary,
    write_validation_outputs,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate layer-1 summary files before using them as evidence.")
    parser.add_argument("summary", type=Path, help="Path to summary.csv or summary_enriched.csv.")
    parser.add_argument("--budgets", nargs="+", type=float, default=None)
    parser.add_argument("--scenarios", nargs="+", default=None)
    parser.add_argument("--modes", nargs="+", default=None)
    parser.add_argument("--profile", default="nominal")
    parser.add_argument("--seed-start", type=int, default=None)
    parser.add_argument("--seeds", type=int, default=None)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--fail-on", choices=["blocker", "major", "warning"], default="major")
    parser.add_argument("--max-time-budget-rate", type=float, default=0.05)
    parser.add_argument("--path-tolerance-m", type=float, default=5.0)
    parser.add_argument("--max-adaptive-equal-share", type=float, default=0.80)
    parser.add_argument("--layer1-defaults", action="store_true", help="Use default layer-1 budgets/scenarios/modes.")
    return parser


def expected_from_args(args: argparse.Namespace) -> ExpectedMatrix | None:
    if args.seed_start is None or args.seeds is None:
        return None
    budgets = tuple(args.budgets if args.budgets is not None else (LAYER1_BUDGETS_M if args.layer1_defaults else ()))
    scenarios = tuple(args.scenarios if args.scenarios is not None else (LAYER1_SCENARIOS if args.layer1_defaults else ()))
    modes = tuple(args.modes if args.modes is not None else (LAYER1_MODES if args.layer1_defaults else ()))
    if not budgets or not scenarios or not modes:
        return None
    return ExpectedMatrix(
        budgets=tuple(float(budget) for budget in budgets),
        scenarios=tuple(str(scenario) for scenario in scenarios),
        modes=tuple(str(mode) for mode in modes),
        profile=str(args.profile),
        seed_start=int(args.seed_start),
        seeds=int(args.seeds),
    )


def main() -> None:
    args = build_parser().parse_args()
    summary = pd.read_csv(args.summary)
    issues = validate_summary(
        summary,
        expected=expected_from_args(args),
        max_time_budget_rate=args.max_time_budget_rate,
        path_tolerance_m=args.path_tolerance_m,
        max_adaptive_equal_share=args.max_adaptive_equal_share,
    )
    if args.out_dir is not None:
        write_validation_outputs(args.out_dir, issues)
    if issues:
        print(issues_to_frame(issues).to_string(index=False))
    payload = validation_summary(issues)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if has_failing_issues(issues, args.fail_on):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
