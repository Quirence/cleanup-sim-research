from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .collection import collect_in_aperture
from .config import RunConfig
from .hydrodynamics import drift_debris
from .mapping import (
    DensityMap,
    init_density_map,
    make_grid,
    predict_density_map,
    suppress_collected_area,
    update_density_map,
)
from .metrics import auc_by_path, map_quality, sensor_metrics, value_at_path
from .planners import (
    choose_goal,
    initial_state,
    pop_route_goal_if_arrived,
    suppress_greedy_goal,
)
from .sensors import detect_with_suite
from .targets import TargetQueue
from .world import DebrisField, make_debris_field, true_count_map


@dataclass
class RunResult:
    config: RunConfig
    field: DebrisField
    density_map: DensityMap
    series: pd.DataFrame
    events: pd.DataFrame
    summary: dict


def _step_toward(pos: np.ndarray, goal: np.ndarray, speed_mps: float, dt_s: float) -> tuple[np.ndarray, float, bool]:
    vec = goal - pos
    dist = float(np.linalg.norm(vec))
    if dist <= 1e-12:
        return pos.copy(), 0.0, True
    step = min(speed_mps * dt_s, dist)
    return pos + vec * (step / dist), step, step >= dist - 1e-12


def _heading(prev: np.ndarray, new: np.ndarray, fallback: float) -> float:
    delta = new - prev
    if np.linalg.norm(delta) <= 1e-12:
        return fallback
    return float(np.arctan2(delta[1], delta[0]))


def run_simulation(config: RunConfig) -> RunResult:
    rng = np.random.default_rng(config.seed)
    grid = make_grid(config.world, config.grid)
    density_map = init_density_map(grid, config.grid, config.world)
    field = make_debris_field(rng, config.world)
    target_queue = TargetQueue(config.planner)
    planner_state = initial_state(config.world, config.planner)

    pos = np.array(config.world.depot, dtype=float)
    heading = 0.0
    current_goal: np.ndarray | None = None
    current_goal_mode = "none"
    current_goal_start_path = 0.0
    current_goal_start_collected = 0
    bin_load_kg = 0.0
    total_path_m = 0.0
    t_s = 0.0
    last_sensor_t_s = -1e9
    stop_reason = "time_budget"

    series: list[dict] = []
    events: list[dict] = []
    detection_records: list[dict] = []

    goal_count = 0
    goal_successes = 0
    empty_goal_arrivals = 0
    route_false_visits = 0
    wasted_path_to_empty_goals = 0.0
    capture_attempts = 0
    missed_captures = 0
    pushed_away_events = 0
    info_gain_total = 0.0
    unload_events = 0

    while t_s <= config.platform.tmax_s and total_path_m <= config.platform.max_path_m:
        predict_density_map(density_map, config.hydro, config.grid, config.platform.dt_s)

        pose = np.array([pos[0], pos[1], heading], dtype=float)
        if t_s - last_sensor_t_s >= config.platform.sensor_period_s:
            last_sensor_t_s = t_s
            detections = detect_with_suite(rng, field, config.world, pose, config.sensors)
            info_gain = update_density_map(density_map, pose, config.sensors.sensors, detections)
            info_gain_total += info_gain
            confirmations = target_queue.add_detections(detections, t_s, config.world)
            for det in detections:
                detection_records.append(
                    {
                        "sensor": det.sensor,
                        "is_false": det.is_false,
                        "source_index": det.source_index,
                        "confidence": det.confidence,
                    }
                )
                events.append(
                    {
                        "time_s": t_s,
                        "event": "detect",
                        "mode": current_goal_mode,
                        "sensor": det.sensor,
                        "x": float(det.position[0]),
                        "y": float(det.position[1]),
                        "confidence": float(det.confidence),
                        "source_index": "" if det.source_index is None else int(det.source_index),
                        "is_false": bool(det.is_false),
                    }
                )
            for track in confirmations:
                events.append(
                    {
                        "time_s": t_s,
                        "event": "target_confirmed",
                        "mode": current_goal_mode,
                        "x": float(track.position[0]),
                        "y": float(track.position[1]),
                        "confidence": float(track.confidence),
                        "hits": int(track.hits),
                    }
                )

        if current_goal is None:
            current_goal, current_goal_mode = choose_goal(
                t_s,
                pos,
                planner_state,
                density_map,
                config.world,
                config.platform,
                config.planner,
                target_queue,
            )
            goal_count += 1
            current_goal_start_path = total_path_m
            current_goal_start_collected = int(field.collected.sum())
            events.append(
                {
                    "time_s": t_s,
                    "event": "goal_started",
                    "mode": current_goal_mode,
                    "x": float(current_goal[0]),
                    "y": float(current_goal[1]),
                    "distance_m": float(np.linalg.norm(current_goal - pos)),
                    "map_value": float(density_map.expected_count[
                        np.argmin(np.abs(grid.y_centers - current_goal[1])),
                        np.argmin(np.abs(grid.x_centers - current_goal[0])),
                    ]),
                }
            )

        speed = config.platform.collection_speed_mps
        prev = pos.copy()
        pos, step_m, arrived = _step_toward(pos, current_goal, speed, config.platform.dt_s)
        heading = _heading(prev, pos, heading)
        total_path_m += step_m

        drift_debris(rng, field, config.world, config.hydro, config.platform.dt_s, robot_pos=pos)
        pushed_away_events = int(field.pushed_events.sum())

        capture_events, bin_load_kg = collect_in_aperture(
            rng,
            field,
            prev,
            pos,
            heading,
            config.platform,
            bin_load_kg,
            config.platform.dt_s,
        )
        if capture_events:
            t_s += config.platform.capture_time_s * len(capture_events)
        for cap in capture_events:
            capture_attempts += 1
            if cap.success:
                suppress_collected_area(density_map, cap.position, max(config.platform.collection_width_m, 1.0))
                events.append(
                    {
                        "time_s": t_s,
                        "event": "collect",
                        "mode": current_goal_mode,
                        "debris_id": cap.debris_id,
                        "x": float(cap.position[0]),
                        "y": float(cap.position[1]),
                        "mass_kg": float(cap.mass_kg),
                        "bin_load_kg": float(bin_load_kg),
                    }
                )
            else:
                missed_captures += 1
                events.append(
                    {
                        "time_s": t_s,
                        "event": cap.reason,
                        "mode": current_goal_mode,
                        "debris_id": cap.debris_id,
                        "x": float(cap.position[0]),
                        "y": float(cap.position[1]),
                        "mass_kg": float(cap.mass_kg),
                    }
                )

        if np.all(field.collected):
            stop_reason = "done"
            events.append({"time_s": t_s, "event": "done", "mode": current_goal_mode, "x": float(pos[0]), "y": float(pos[1])})
            break

        if bin_load_kg >= config.platform.bin_capacity_kg * config.platform.return_ratio:
            current_goal = np.array(config.world.depot, dtype=float)
            current_goal_mode = "return"

        if arrived or (current_goal is not None and np.linalg.norm(current_goal - pos) <= config.platform.arrival_tolerance_m):
            collected_delta = int(field.collected.sum()) - current_goal_start_collected
            goal_path = total_path_m - current_goal_start_path
            if current_goal_mode == "greedy":
                suppress_greedy_goal(planner_state, density_map, current_goal, config.planner.greedy_tabu_radius_m)
            counts_for_goal_metrics = current_goal_mode != "return"
            if counts_for_goal_metrics:
                if collected_delta > 0:
                    goal_successes += 1
                else:
                    empty_goal_arrivals += 1
                    wasted_path_to_empty_goals += goal_path
                    if current_goal_mode == "route":
                        route_false_visits += 1
            events.append(
                {
                    "time_s": t_s,
                    "event": "goal_completed",
                    "mode": current_goal_mode,
                    "x": float(pos[0]),
                    "y": float(pos[1]),
                    "collected_delta": collected_delta,
                    "goal_path_m": float(goal_path),
                    "empty_goal": collected_delta == 0,
                }
            )
            if np.linalg.norm(pos - np.array(config.world.depot, dtype=float)) <= config.platform.arrival_tolerance_m and bin_load_kg > 0:
                unload_events += 1
                events.append(
                    {
                        "time_s": t_s,
                        "event": "unload",
                        "mode": current_goal_mode,
                        "x": float(pos[0]),
                        "y": float(pos[1]),
                        "bin_load_kg": float(bin_load_kg),
                    }
                )
                bin_load_kg = 0.0
            pop_route_goal_if_arrived(planner_state, pos, config.platform.arrival_tolerance_m, target_queue)
            current_goal = None

        collected_count = int(field.collected.sum())
        series.append(
            {
                "time_s": t_s,
                "path_m": total_path_m,
                "collected": collected_count,
                "collected_ratio": collected_count / max(1, config.world.n_debris),
                "bin_load_kg": bin_load_kg,
                "mode": current_goal_mode,
                "empty_goal_arrivals": empty_goal_arrivals,
                "route_false_visits": route_false_visits,
                "wasted_path_to_empty_goals": wasted_path_to_empty_goals,
            }
        )

        t_s += config.platform.dt_s

    if total_path_m >= config.platform.max_path_m and stop_reason != "done":
        stop_reason = "path_budget"

    residual_counts = true_count_map(field, grid.x_edges, grid.y_edges, include_collected=False)
    quality = map_quality(density_map, residual_counts)
    collected_count = int(field.collected.sum())
    collected_ratio = collected_count / max(1, config.world.n_debris)
    path_values = [float(s["path_m"]) for s in series]
    ratios = [float(s["collected_ratio"]) for s in series]
    detection_summary = sensor_metrics(detection_records, config.world.n_debris)
    summary = {
        "scenario": config.scenario,
        "profile": config.profile,
        "mode": config.planner.mode,
        "seed": config.seed,
        "stop_reason": stop_reason,
        "collected": collected_count,
        "collected_ratio": collected_ratio,
        "collected_mass_kg": float(field.masses_kg[field.collected].sum()),
        "collected_mass_per_meter": float(field.masses_kg[field.collected].sum()) / max(1e-9, total_path_m),
        "path_length_m": total_path_m,
        "sim_time_s": t_s,
        "goal_count": goal_count,
        "empty_goal_arrivals": empty_goal_arrivals,
        "wasted_path_to_empty_goals": wasted_path_to_empty_goals,
        "goal_success_rate": goal_successes / max(1, goal_count),
        "route_false_visits": route_false_visits,
        "capture_attempts": capture_attempts,
        "missed_captures": missed_captures,
        "collection_precision": (capture_attempts - missed_captures) / max(1, capture_attempts),
        "pushed_away_events": pushed_away_events,
        "info_gain_total": info_gain_total,
        "unload_events": unload_events,
        "auc_collected_by_path": auc_by_path(path_values, ratios, config.platform.max_path_m),
        "collected_ratio_at_1km": value_at_path(path_values, ratios, 1000.0),
        "collected_ratio_at_2km": value_at_path(path_values, ratios, 2000.0),
        "collected_ratio_at_3km": value_at_path(path_values, ratios, 3000.0),
    }
    summary.update(quality)
    summary.update(detection_summary)
    return RunResult(
        config=config,
        field=field,
        density_map=density_map,
        series=pd.DataFrame(series),
        events=pd.DataFrame(events),
        summary=summary,
    )
