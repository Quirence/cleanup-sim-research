from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import pandas as pd

from .config import PlannerConfig, RunConfig


@dataclass(frozen=True)
class SensitivityCase:
    name: str
    parameter: str | None
    value: int | float | None


SENSITIVITY_VALUES: dict[str, tuple[int | float, ...]] = {
    "target_confirm_hits": (1, 2, 3),
    "detected_confirm_prob": (0.65, 0.72, 0.8),
    "target_false_suppress_radius_m": (8.0, 12.0, 16.0),
    "hybrid_explore_entropy_threshold": (0.12, 0.18, 0.24),
}

SENSITIVITY_METRICS: tuple[str, ...] = (
    "collected_ratio",
    "auc_collected_by_path",
    "path_length_m",
    "false_visits",
    "target_confirmed",
    "target_route_attempts",
    "target_visit_successes",
    "target_visit_false",
    "target_precision",
    "map_f1",
    "map_iou",
    "brier_score",
    "final_entropy",
    "collected_ratio_at_2km",
    "collected_ratio_at_4km",
    "collected_ratio_at_6km",
    "collected_ratio_at_8km",
    "collected_ratio_at_10km",
    "collected_ratio_at_12km",
)


def iter_sensitivity_cases(base_planner: PlannerConfig) -> list[SensitivityCase]:
    cases = [SensitivityCase(name="baseline", parameter=None, value=None)]
    for parameter, values in SENSITIVITY_VALUES.items():
        baseline_value = getattr(base_planner, parameter)
        for value in values:
            if value == baseline_value:
                continue
            cases.append(SensitivityCase(name=f"{parameter}={value}", parameter=parameter, value=value))
    return cases


def apply_sensitivity_case(config: RunConfig, case: SensitivityCase) -> RunConfig:
    if case.parameter is None:
        return replace(config, planner=replace(config.planner, mode="hybrid"))
    updates: dict[str, Any] = {"mode": "hybrid", case.parameter: case.value}
    return replace(config, planner=replace(config.planner, **updates))


def cases_to_frame(cases: list[SensitivityCase]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sensitivity_case": case.name,
            "sensitivity_parameter": case.parameter or "baseline",
            "sensitivity_value": case.value,
        }
        for case in cases
    )


def aggregate_sensitivity_summary(summary: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    group_cols = ["scenario", "sensitivity_case", "sensitivity_parameter", "sensitivity_value"]
    for keys, group in summary.groupby(group_cols, dropna=False):
        scenario, case_name, parameter, value = keys
        row: dict[str, Any] = {
            "scenario": scenario,
            "sensitivity_case": case_name,
            "sensitivity_parameter": parameter,
            "sensitivity_value": value,
            "runs": int(len(group)),
        }
        for metric in SENSITIVITY_METRICS:
            if metric in group:
                row[f"{metric}_mean"] = float(group[metric].mean(skipna=True))
                row[f"{metric}_std"] = float(group[metric].std(skipna=True))
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["scenario", "sensitivity_case"]).reset_index(drop=True)
