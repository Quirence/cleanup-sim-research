"""Observable mission diagnostics; definitions in docs/project/regime_metrics.md."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .config import RunConfig
from .hydrodynamics import ambient_velocity
from .layer1 import regime_metrics_for_config
from .mapping import DensityMap
from .provenance import json_sha256
from .targets import TargetTrack


SNAPSHOT_VERSION = 1
SNAPSHOT_METRICS = (
    "response_time_nominal_s", "drift_response_width", "diffusion_response_width",
    "fresh_age_limit_s", "reachable_radius_m", "reachable_area_m2",
    "fresh_target_count", "fresh_target_density_per_m2", "fresh_target_sigma_width_median",
    "map_concentration", "queued_route_points", "queued_route_length_m",
    "queued_route_time_nominal_s", "route_staleness_ratio", "route_drift_width",
)


def ratio(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator > 0 else math.nan


def map_concentration(expected_count: np.ndarray) -> float:
    """Normalized Simpson concentration, not calibration or map accuracy."""
    values = np.asarray(expected_count, dtype=float).ravel()
    if np.any(~np.isfinite(values)) or np.any(values < 0):
        raise ValueError("Map counts must be finite and nonnegative.")
    mass = float(values.sum())
    if values.size <= 1 or mass <= 0:
        return math.nan
    p = values / mass
    return float(np.clip((len(p) * np.dot(p, p) - 1.0) / (len(p) - 1.0), 0.0, 1.0))


def goal_snapshot(
    cfg: RunConfig, time_s: float, position: np.ndarray, goal: np.ndarray,
    density_map: DensityMap, tracks: list[TargetTrack],
    route: list[np.ndarray] | None, path_m: float,
) -> dict:
    """Read-only snapshot after choosing a goal; no truth-field or RNG access."""
    width = cfg.platform.collection_width_m
    speed = cfg.platform.collection_speed_mps
    if width <= 0 or speed <= 0 or cfg.planner.target_stale_after_s <= 0:
        raise ValueError("Regime metrics need positive collection width/speed and track lifetime.")
    drift = float(np.linalg.norm(ambient_velocity(cfg.hydro)))
    response = cfg.platform.sensor_period_s + float(np.linalg.norm(goal - position)) / speed
    fresh_age = min(cfg.planner.target_stale_after_s, width / drift if drift > 0 else math.inf)
    radius = min(max(sensor.range_m for sensor in cfg.sensors.sensors), max(0.0, cfg.platform.max_path_m - path_m))
    grid = density_map.grid
    mask = (grid.xx - position[0]) ** 2 + (grid.yy - position[1]) ** 2 <= radius ** 2
    area = float(mask.sum() * grid.dx * grid.dy) if radius > 0 else 0.0
    fresh = [track for track in tracks if (
        track.confirmed(cfg.planner) and 0 <= time_s - track.last_seen_s <= fresh_age
        and np.linalg.norm(track.position - position) <= radius
    )]
    # Empty queue means no committed multi-leg route. Do not invent a route
    # from adaptive scores or the straight-line distance to the current goal.
    points = [] if route is None else route
    length = sum(float(np.linalg.norm(b - a)) for a, b in zip([position, *points], points))
    route_time = length / speed + len(points) * cfg.platform.target_dwell_time_s
    metrics = {
        "response_time_nominal_s": response,
        "drift_response_width": drift * response / width,
        "diffusion_response_width": math.sqrt(max(0.0, 4 * cfg.hydro.diffusivity_m2_s * response)) / width,
        "fresh_age_limit_s": fresh_age,
        "reachable_radius_m": radius,
        "reachable_area_m2": area,
        "fresh_target_count": len(fresh),
        "fresh_target_density_per_m2": ratio(len(fresh), area),
        "fresh_target_sigma_width_median": float(np.median([t.localization_sigma_m for t in fresh]) / width) if fresh else math.nan,
        "map_concentration": map_concentration(density_map.expected_count),
        "queued_route_points": len(points),
        "queued_route_length_m": length,
        "queued_route_time_nominal_s": route_time,
        "route_staleness_ratio": route_time / cfg.planner.target_stale_after_s,
        "route_drift_width": drift * route_time / width,
    }
    return {"regime_snapshot_version": SNAPSHOT_VERSION, **{f"regime_{key}": value for key, value in metrics.items()}}


def run_metrics(cfg: RunConfig, summary: dict, events: pd.DataFrame) -> dict:
    """Configuration cues, goal-start means, and explicitly ex-post outcomes."""
    result = {f"regime_config_{key}": value for key, value in regime_metrics_for_config(cfg).items()}
    clutter_scan = sum(result[f"regime_config_expected_{sensor}_clutter_per_scan"] for sensor in ("camera", "radar"))
    result["regime_config_expected_clutter_per_s"] = ratio(clutter_scan, cfg.platform.sensor_period_s)
    result["regime_config_debris_density_per_m2"] = ratio(cfg.world.n_debris, cfg.world.width_m * cfg.world.height_m)
    path = float(summary["path_length_m"])
    result.update({
        "regime_outcome_empty_visit_fraction": ratio(summary["empty_goal_arrivals"], summary["evaluated_goal_count"]),
        "regime_outcome_wasted_path_fraction": ratio(summary["wasted_path_to_empty_goals"], path),
        "regime_outcome_false_marks_per_km": ratio(1000 * summary["false_detection_count"], path),
        "regime_outcome_false_to_true_marks": ratio(summary["false_detection_count"], summary["true_detection_count"]),
    })
    completed = events.loc[(events["event"] == "goal_completed") & (events["mode"] != "return")] if {"event", "mode"} <= set(events) else events.iloc[:0]
    durations = pd.to_numeric(completed.get("goal_time_s", pd.Series(dtype=float)), errors="coerce")
    durations = durations[np.isfinite(durations) & (durations >= 0)]
    result["regime_outcome_completed_leg_n"] = len(durations)
    result["regime_outcome_mean_completed_leg_time_s"] = float(durations.mean()) if len(durations) else math.nan
    result["regime_outcome_mean_completed_leg_drift_width"] = (
        result["regime_config_drift_speed_mps"] * result["regime_outcome_mean_completed_leg_time_s"] / cfg.platform.collection_width_m
    )
    starts = events.loc[events["event"] == "goal_started"] if "event" in events else events.iloc[:0]
    versions = pd.to_numeric(starts.get("regime_snapshot_version", pd.Series(index=starts.index, dtype=float)), errors="coerce")
    snapshots = starts.loc[versions == SNAPSHOT_VERSION]
    result["regime_goal_start_count"] = len(starts)
    result["regime_goal_snapshot_count"] = len(snapshots)
    result["regime_goal_snapshot_coverage"] = ratio(len(snapshots), len(starts))
    for key in SNAPSHOT_METRICS:
        values = pd.to_numeric(snapshots.get(f"regime_{key}", pd.Series(dtype=float)), errors="coerce")
        values = values[np.isfinite(values)]
        result[f"regime_goal_start_mean_{key}"] = float(values.mean()) if len(values) else math.nan
        result[f"regime_goal_start_valid_n_{key}"] = len(values)
    return result


def oracle_pair_key(config: dict, provenance: dict) -> str | None:
    """Same non-planner configuration and execution identity; no loose seed join."""
    if provenance.get("git_dirty") is not False or any(
        not provenance.get(key) or provenance[key] == "unknown"
        for key in ("git_commit_full", "source_sha256", "environment_sha256")
    ):
        return None
    # Planner settings differ by strategy; all platform/sensor/hydro/grid/world
    # settings, seed, scenario and profile must match in full.
    return json_sha256({
        "configuration_without_planner": {key: value for key, value in config.items() if key != "planner"},
        "identity": {key: provenance[key] for key in ("git_commit_full", "source_sha256", "environment_sha256")},
    })


def add_oracle_gaps(rows: list[dict]) -> list[dict]:
    oracle = {}
    seen = set()
    for row in rows:
        key = row.get("oracle_pair_key")
        if key and (key, row["mode"]) in seen:
            raise ValueError("Duplicate compatible runs; select one repeat per mode/configuration.")
        seen.add((key, row["mode"]))
        if key and row["mode"] == "oracle_current_physics":
            oracle[key] = row
    result = []
    for row in rows:
        reference = oracle.get(row.get("oracle_pair_key"))
        result.append({
            **row,
            "regime_oracle_available": reference is not None,
            "regime_oracle_gap_auc": reference["auc_collected_by_path"] - row["auc_collected_by_path"] if reference else math.nan,
            "regime_oracle_gap_collected_ratio": reference["collected_ratio"] - row["collected_ratio"] if reference else math.nan,
        })
    return result
