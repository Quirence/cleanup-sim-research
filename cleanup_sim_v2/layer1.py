from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .config import PlatformConfig, RunConfig, SensorConfig, scenario_config
from .hydrodynamics import ambient_velocity


LAYER1_BUDGETS_M: tuple[float, ...] = (1200.0, 2400.0, 3600.0, 7200.0)
LAYER1_SCENARIOS: tuple[str, ...] = ("static_calm", "weak_drift", "strong_drift", "robot_disturbed")
LAYER1_MODES: tuple[str, ...] = (
    "lawnmower_collect",
    "greedy",
    "confirmed_route",
    "belief_horizon",
    "belief_orienteering",
    "belief_orienteering_depth1",
    "adaptive_mission",
    "oracle_current_physics",
)
FIXED_REGIME_MODES: tuple[str, ...] = (
    "lawnmower_collect",
    "greedy",
    "confirmed_route",
    "belief_horizon",
    "belief_orienteering",
    "belief_orienteering_depth1",
)
ORACLE_MODE = "oracle_current_physics"

# These values are intentionally identical to the layer-1 protocol table. For custom budgets,
# fall back to the published formula below.
LAYER1_TMAX_OVERRIDES_S: dict[float, float] = {
    1200.0: 8000.0,
    2400.0: 13200.0,
    3600.0: 20000.0,
    7200.0: 40000.0,
}


def safety_tmax_s(path_budget_m: float, collection_speed_mps: float = PlatformConfig().collection_speed_mps) -> float:
    """Return the layer-1 safety time limit for a path budget.

    Standard layer-1 budgets use the explicitly documented values. Non-standard budgets use
    max(8000, ceil(3.3 * path_budget / collection_speed)).
    """
    key = float(path_budget_m)
    if key in LAYER1_TMAX_OVERRIDES_S:
        return LAYER1_TMAX_OVERRIDES_S[key]
    return float(max(8000, math.ceil(3.3 * path_budget_m / max(collection_speed_mps, 1e-9))))


def with_budget(cfg: RunConfig, path_budget_m: float, tmax_s: float | None = None) -> RunConfig:
    tmax = safety_tmax_s(path_budget_m, cfg.platform.collection_speed_mps) if tmax_s is None else tmax_s
    return replace(
        cfg,
        platform=replace(
            cfg.platform,
            max_path_m=float(path_budget_m),
            tmax_s=float(tmax),
        ),
    )


def sector_area_m2(sensor: SensorConfig) -> float:
    return 0.5 * math.radians(sensor.fov_deg) * sensor.range_m * sensor.range_m


def effective_localization_sigma_m(sensor: SensorConfig) -> float:
    """Use the detector decay range as a transparent reference distance for sensitivity ratios."""
    return float(sensor.localization_sigma_m + sensor.localization_sigma_per_m * sensor.decay_range_m)


def regime_metrics_for_config(cfg: RunConfig, path_budget_m: float | None = None) -> dict[str, float]:
    budget = cfg.platform.max_path_m if path_budget_m is None else float(path_budget_m)
    world_area = float(cfg.world.width_m * cfg.world.height_m)
    width = max(float(cfg.platform.collection_width_m), 1e-9)
    drift_speed = float(np.linalg.norm(ambient_velocity(cfg.hydro)))
    camera_sigma = effective_localization_sigma_m(cfg.sensors.camera)
    radar_sigma = effective_localization_sigma_m(cfg.sensors.radar)
    return {
        "path_budget_m": budget,
        "safety_tmax_s": float(cfg.platform.tmax_s),
        "world_area_m2": world_area,
        "collection_coverage_ratio": float(budget * width / max(world_area, 1e-9)),
        "drift_speed_mps": drift_speed,
        "drift_per_update_width": float(drift_speed * cfg.platform.sensor_period_s / width),
        "drift_per_60s_width": float(drift_speed * 60.0 / width),
        "camera_sigma_eff_m": camera_sigma,
        "radar_sigma_eff_m": radar_sigma,
        "camera_capture_uncertainty_ratio": float(camera_sigma / width),
        "radar_capture_uncertainty_ratio": float(radar_sigma / width),
        "expected_camera_clutter_per_scan": float(cfg.sensors.camera.clutter_rate_per_m2 * sector_area_m2(cfg.sensors.camera)),
        "expected_radar_clutter_per_scan": float(cfg.sensors.radar.clutter_rate_per_m2 * sector_area_m2(cfg.sensors.radar)),
    }


def layer1_config(scenario: str, seed: int, mode: str, path_budget_m: float, profile: str = "nominal") -> RunConfig:
    cfg = scenario_config(scenario, seed, mode, profile)  # type: ignore[arg-type]
    return with_budget(cfg, path_budget_m)


def enrich_summary(summary: pd.DataFrame) -> pd.DataFrame:
    if summary.empty:
        return summary.copy()
    df = summary.copy()
    for column in ("path_budget_m", "scenario", "profile", "seed", "mode"):
        if column not in df.columns:
            raise ValueError(f"summary is missing required column: {column}")
    df = _add_regret_columns(df)
    return df


def _add_regret_columns(summary: pd.DataFrame) -> pd.DataFrame:
    regret_cols = [
        "best_fixed_auc_collected_by_path",
        "best_fixed_collected_ratio",
        "regret_to_best_fixed_auc",
        "regret_to_best_fixed_collected_ratio",
    ]
    df = summary.drop(columns=[col for col in regret_cols if col in summary.columns]).copy()
    group_cols = ["path_budget_m", "scenario", "profile", "seed"]
    fixed = df[df["mode"].isin(FIXED_REGIME_MODES)]
    if fixed.empty:
        df["best_fixed_auc_collected_by_path"] = math.nan
        df["best_fixed_collected_ratio"] = math.nan
        df["regret_to_best_fixed_auc"] = math.nan
        df["regret_to_best_fixed_collected_ratio"] = math.nan
        return df

    best_auc = fixed.groupby(group_cols)["auc_collected_by_path"].max().rename("best_fixed_auc_collected_by_path")
    best_collected = fixed.groupby(group_cols)["collected_ratio"].max().rename("best_fixed_collected_ratio")
    df = df.merge(best_auc, on=group_cols, how="left").merge(best_collected, on=group_cols, how="left")
    df["regret_to_best_fixed_auc"] = df["best_fixed_auc_collected_by_path"] - df["auc_collected_by_path"]
    df["regret_to_best_fixed_collected_ratio"] = df["best_fixed_collected_ratio"] - df["collected_ratio"]
    return df


def evaluate_budget_calibration(summary: pd.DataFrame) -> pd.DataFrame:
    if summary.empty:
        return pd.DataFrame()
    df = enrich_summary(summary)
    rows: list[dict] = []
    for budget, bdf in df.groupby("path_budget_m", sort=True):
        non_oracle = bdf[bdf["mode"] != ORACLE_MODE]
        time_budget_rate = float((non_oracle["stop_reason"] == "time_budget").mean()) if not non_oracle.empty else math.nan

        oracle = bdf[bdf["mode"] == ORACLE_MODE]
        oracle_by_scenario = oracle.groupby("scenario")["collected_ratio"].median()
        oracle_scenarios_ge_090 = int((oracle_by_scenario >= 0.90).sum())

        non_oracle_medians = non_oracle.groupby(["scenario", "mode"])["collected_ratio"].median()
        best_non_oracle_by_scenario = non_oracle_medians.groupby("scenario").max()
        nonsaturated_scenarios = int((best_non_oracle_by_scenario < 0.85).sum())

        auc_medians = non_oracle.groupby(["scenario", "mode"])["auc_collected_by_path"].median()
        distinct_scenarios = 0
        for _, scenario_values in auc_medians.groupby(level="scenario"):
            values = scenario_values.sort_values(ascending=False).to_numpy(dtype=float)
            if values.size >= 3 and values[0] - values[2] >= 0.05:
                distinct_scenarios += 1

        passes = (
            time_budget_rate <= 0.05
            and oracle_scenarios_ge_090 >= 3
            and nonsaturated_scenarios >= 3
            and distinct_scenarios >= 2
        )
        rows.append(
            {
                "path_budget_m": float(budget),
                "time_budget_rate_non_oracle": time_budget_rate,
                "oracle_scenarios_median_ge_0_90": oracle_scenarios_ge_090,
                "nonsaturated_best_non_oracle_scenarios": nonsaturated_scenarios,
                "distinct_auc_scenarios": distinct_scenarios,
                "passes_layer1_budget_gate": bool(passes),
            }
        )
    return pd.DataFrame(rows)


def select_nominal_budget(calibration: pd.DataFrame) -> float | None:
    if calibration.empty or "passes_layer1_budget_gate" not in calibration.columns:
        return None
    passed = calibration[calibration["passes_layer1_budget_gate"]].sort_values("path_budget_m")
    if passed.empty:
        return None
    return float(passed.iloc[0]["path_budget_m"])


def adaptive_policy_shares(run_dirs: Iterable[Path]) -> pd.DataFrame:
    rows: list[dict] = []
    for run_dir in run_dirs:
        for events_path in sorted(run_dir.rglob("*_events.csv")):
            events = pd.read_csv(events_path)
            if "adaptive_selected_policy" not in events.columns:
                continue
            policies = events["adaptive_selected_policy"].dropna()
            if policies.empty:
                continue
            parts = events_path.name.split("__")
            scenario = parts[0] if len(parts) >= 1 else "unknown"
            mode = parts[1] if len(parts) >= 2 else "unknown"
            seed_part = next((part for part in parts if part.startswith("seed")), "seed")
            seed = int(seed_part.removeprefix("seed").split("_")[0]) if seed_part != "seed" else -1
            counts = policies.value_counts()
            total = int(counts.sum())
            for policy, count in counts.items():
                rows.append(
                    {
                        "scenario": scenario,
                        "mode": mode,
                        "seed": seed,
                        "adaptive_selected_policy": str(policy),
                        "count": int(count),
                        "share": float(count / max(1, total)),
                    }
                )
    return pd.DataFrame(rows)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
