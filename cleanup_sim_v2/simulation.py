from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .collection import CaptureEvent, collect_in_aperture
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
from .sensors import detect_with_suite, wrap_angle
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


def _advance_motion(
    pos: np.ndarray,
    goal: np.ndarray,
    heading_rad: float,
    speed_mps: float,
    dt_s: float,
    turn_rate_rad_s: float,
) -> tuple[np.ndarray, float, float, bool]:
    vec = goal - pos
    dist = float(np.linalg.norm(vec))
    if dist <= 1e-12:
        return pos.copy(), heading_rad, 0.0, True

    desired_heading = float(np.arctan2(vec[1], vec[0]))
    heading_error = float(wrap_angle(desired_heading - heading_rad))
    max_turn = max(0.0, turn_rate_rad_s) * dt_s
    if abs(heading_error) > max_turn + 1e-12:
        return pos.copy(), float(wrap_angle(heading_rad + np.sign(heading_error) * max_turn)), 0.0, False

    step = min(max(0.0, speed_mps) * dt_s, dist)
    new_pos = pos + vec * (step / max(dist, 1e-12))
    return new_pos, desired_heading, step, step >= dist - 1e-12


def _motion_speed(
    config: RunConfig,
    goal_mode: str,
    pos: np.ndarray,
    goal: np.ndarray,
    goal_details: dict[str, float | str] | None = None,
) -> float:
    if goal_mode == "return":
        return config.platform.cruise_speed_mps
    if config.planner.mode == "lawnmower_collect":
        return config.platform.collection_speed_mps
    details = {} if goal_details is None else goal_details
    candidate_type = str(details.get("candidate_type", ""))
    expected_collection = float(details.get("score_expected_collection", 0.0))
    is_collection_transect = candidate_type in {
        "confirmed_target_transect",
        "provisional_target_transect",
        "density_transect",
        "cluster_route_transect",
        "confirmed_target_local_sweep",
    }
    if (
        config.planner.belief_transect_collection_speed_enabled
        and goal_mode in {"belief_horizon", "belief_orienteering"}
        and (
            is_collection_transect
            or expected_collection >= config.planner.belief_collection_speed_expected_count_threshold
        )
    ):
        return config.platform.collection_speed_mps
    if goal_mode in {"greedy", "active", "belief_horizon", "belief_orienteering", "route", "oracle"}:
        distance = float(np.linalg.norm(goal - pos))
        if distance <= config.platform.collection_approach_radius_m:
            return config.platform.collection_speed_mps
        return config.platform.cruise_speed_mps
    return config.platform.cruise_speed_mps


def _is_belief_goal_mode(goal_mode: str) -> bool:
    return goal_mode in {"belief_horizon", "belief_orienteering"}


def _grid_value(density_map: DensityMap, point: np.ndarray) -> float:
    grid = density_map.grid
    iy = int(np.argmin(np.abs(grid.y_centers - point[1])))
    ix = int(np.argmin(np.abs(grid.x_centers - point[0])))
    return float(density_map.expected_count[iy, ix])


def _append_capture_event(
    events: list[dict],
    cap: CaptureEvent,
    t_s: float,
    mode: str,
    bin_load_kg: float,
) -> None:
    row = {
        "time_s": t_s,
        "event": "collect" if cap.success else cap.reason,
        "mode": mode,
        "debris_id": cap.debris_id,
        "x": float(cap.position[0]),
        "y": float(cap.position[1]),
        "mass_kg": float(cap.mass_kg),
        "work_kg": float(cap.work_kg),
        "required_work_kg": float(cap.required_work_kg),
        "terminal_capture": bool(cap.terminal),
    }
    if cap.success:
        row["bin_load_kg"] = float(bin_load_kg)
    events.append(row)


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
    current_goal_reason = "none"
    current_goal_expected_value = 0.0
    current_goal_details: dict[str, float | str] = {}
    current_goal_start_path = 0.0
    current_goal_start_time = 0.0
    current_goal_arrived_time: float | None = None
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
    evaluated_goal_count = 0
    goal_successes = 0
    empty_goal_arrivals = 0
    route_false_visits = 0
    wasted_path_to_empty_goals = 0.0
    wasted_time_to_empty_goals = 0.0
    capture_contacts = 0
    terminal_capture_attempts = 0
    successful_captures = 0
    missed_capture_count = 0
    bin_full_events = 0
    throughput_limit_events = 0
    partial_contact_events = 0
    pushed_away_events = 0
    info_gain_total = 0.0
    unload_events = 0

    while t_s <= config.platform.tmax_s and total_path_m <= config.platform.max_path_m:
        dt_s = config.platform.dt_s
        predict_density_map(density_map, config.hydro, config.grid, dt_s)
        if config.planner.belief_track_prediction_enabled:
            target_queue.predict(config.hydro, config.world, dt_s)
        target_queue.prune(t_s)

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
                        "range_m": det.range_m,
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
                        "range_m": float(det.range_m),
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
            decision = choose_goal(
                t_s,
                pos,
                planner_state,
                density_map,
                config.world,
                config.platform,
                config.planner,
                target_queue,
                field,
            )
            current_goal = decision.point
            current_goal_mode = decision.mode
            current_goal_reason = decision.reason
            current_goal_expected_value = decision.expected_value
            current_goal_details = dict(decision.details)
            goal_count += 1
            current_goal_start_path = total_path_m
            current_goal_start_time = t_s
            current_goal_arrived_time = None
            current_goal_start_collected = int(field.collected.sum())
            row = {
                "time_s": t_s,
                "event": "goal_started",
                "mode": current_goal_mode,
                "reason": current_goal_reason,
                "x": float(current_goal[0]),
                "y": float(current_goal[1]),
                "distance_m": float(np.linalg.norm(current_goal - pos)),
                "map_value": _grid_value(density_map, current_goal),
                "expected_value": float(current_goal_expected_value),
            }
            row.update(current_goal_details)
            events.append(row)
        elif config.planner.mode == "oracle_current_physics" and current_goal_mode == "oracle":
            decision = choose_goal(
                t_s,
                pos,
                planner_state,
                density_map,
                config.world,
                config.platform,
                config.planner,
                target_queue,
                field,
            )
            if np.linalg.norm(decision.point - current_goal) > config.platform.arrival_tolerance_m:
                current_goal = decision.point
                current_goal_reason = decision.reason
                current_goal_expected_value = decision.expected_value
                current_goal_details = dict(decision.details)
                current_goal_arrived_time = None
                events.append(
                    {
                        "time_s": t_s,
                        "event": "goal_updated",
                        "mode": current_goal_mode,
                        "reason": current_goal_reason,
                        "x": float(current_goal[0]),
                        "y": float(current_goal[1]),
                        "distance_m": float(np.linalg.norm(current_goal - pos)),
                        "expected_value": float(current_goal_expected_value),
                    }
                )

        arrived = False
        substeps = max(1, int(config.platform.physics_substeps))
        dt_sub = dt_s / substeps
        for substep in range(substeps):
            if current_goal is None:
                break
            speed = _motion_speed(config, current_goal_mode, pos, current_goal, current_goal_details)
            prev = pos.copy()
            pos, heading, step_m, sub_arrived = _advance_motion(
                pos,
                current_goal,
                heading,
                speed,
                dt_sub,
                config.platform.turn_rate_rad_s,
            )
            total_path_m += step_m

            sub_t_s = t_s + (substep + 1) * dt_sub
            drift_debris(rng, field, config.world, config.hydro, dt_sub, robot_pos=pos)
            pushed_away_events = int(field.pushed_events.sum())

            capture_events, bin_load_kg = collect_in_aperture(
                rng,
                field,
                prev,
                pos,
                heading,
                config.platform,
                bin_load_kg,
                dt_sub,
                speed_mps=speed,
            )
            for cap in capture_events:
                capture_contacts += 1
                if cap.reason == "partial_contact":
                    partial_contact_events += 1
                elif cap.reason == "throughput_limit":
                    throughput_limit_events += 1
                elif cap.reason == "bin_full":
                    bin_full_events += 1
                if cap.terminal and cap.reason in {"captured", "missed_capture"}:
                    terminal_capture_attempts += 1
                if cap.success:
                    successful_captures += 1
                    suppress_collected_area(density_map, cap.position, max(config.platform.collection_width_m, 1.0))
                elif cap.reason == "missed_capture":
                    missed_capture_count += 1
                _append_capture_event(events, cap, sub_t_s, current_goal_mode, bin_load_kg)

            arrived = arrived or sub_arrived
            if np.all(field.collected) or total_path_m >= config.platform.max_path_m:
                break

        if np.all(field.collected):
            stop_reason = "done"
            events.append(
                {
                    "time_s": t_s,
                    "event": "done",
                    "mode": current_goal_mode,
                    "x": float(pos[0]),
                    "y": float(pos[1]),
                }
            )
            break

        if bin_load_kg >= config.platform.bin_capacity_kg * config.platform.return_ratio and current_goal_mode != "return":
            current_goal = np.array(config.world.depot, dtype=float)
            current_goal_mode = "return"
            current_goal_reason = "bin_capacity_return"
            current_goal_expected_value = 0.0
            current_goal_details = {}
            current_goal_start_path = total_path_m
            current_goal_start_time = t_s + dt_s
            current_goal_arrived_time = None
            current_goal_start_collected = int(field.collected.sum())
            events.append(
                {
                    "time_s": t_s + dt_s,
                    "event": "return_started",
                    "mode": "return",
                    "reason": current_goal_reason,
                    "x": float(current_goal[0]),
                    "y": float(current_goal[1]),
                    "bin_load_kg": float(bin_load_kg),
                }
            )

        reached_goal_region = current_goal is not None and (
            arrived or np.linalg.norm(current_goal - pos) <= config.platform.arrival_tolerance_m
        )
        if reached_goal_region and current_goal_arrived_time is None:
            current_goal_arrived_time = t_s + dt_s

        dwell_required = current_goal_mode in {"greedy", "active", "belief_horizon", "belief_orienteering", "route", "oracle"}
        collected_delta_now = int(field.collected.sum()) - current_goal_start_collected
        dwell_elapsed = 0.0 if current_goal_arrived_time is None else (t_s + dt_s - current_goal_arrived_time)
        should_complete_goal = bool(reached_goal_region)
        if dwell_required and collected_delta_now == 0 and dwell_elapsed < config.platform.target_dwell_time_s:
            should_complete_goal = False

        if current_goal is not None and should_complete_goal:
            collected_delta = int(field.collected.sum()) - current_goal_start_collected
            goal_path = total_path_m - current_goal_start_path
            goal_time = t_s + dt_s - current_goal_start_time
            candidate_type = current_goal_details.get("candidate_type")
            is_refinement_goal = (
                _is_belief_goal_mode(current_goal_mode)
                and str(candidate_type).endswith("_refine")
            )
            is_cluster_route_goal = candidate_type == "cluster_route_transect"
            is_transect_goal = candidate_type in {
                "confirmed_target_transect",
                "provisional_target_transect",
                "density_transect",
                "confirmed_target_local_sweep",
                "cluster_route_transect",
            }
            empty_suppression_radius = config.planner.target_suppression_radius_m
            if _is_belief_goal_mode(current_goal_mode) and is_transect_goal:
                empty_suppression_radius = max(
                    empty_suppression_radius,
                    config.planner.belief_transect_extension_m + config.planner.target_suppression_radius_m,
                )
            if current_goal_mode == "greedy":
                suppress_greedy_goal(planner_state, density_map, current_goal, config.planner.greedy_tabu_radius_m)
            elif _is_belief_goal_mode(current_goal_mode) and collected_delta == 0 and not is_refinement_goal:
                suppress_greedy_goal(
                    planner_state,
                    density_map,
                    current_goal,
                    max(empty_suppression_radius, 0.5 * config.planner.candidate_spacing_m),
                )
            counts_for_goal_metrics = current_goal_mode != "return" and not is_refinement_goal
            if counts_for_goal_metrics:
                evaluated_goal_count += 1
                if collected_delta > 0:
                    goal_successes += 1
                    if _is_belief_goal_mode(current_goal_mode) and is_transect_goal:
                        target_queue.remove_near(current_goal, empty_suppression_radius)
                        if not is_cluster_route_goal:
                            planner_state.current_route = None
                            planner_state.current_route_mode = "route"
                            planner_state.current_route_reason = "confirmed_target_route"
                            planner_state.current_route_details = {}
                else:
                    empty_goal_arrivals += 1
                    wasted_path_to_empty_goals += goal_path
                    wasted_time_to_empty_goals += goal_time
                    target_queue.suppress_near(current_goal, t_s + dt_s, empty_suppression_radius)
                    if _is_belief_goal_mode(current_goal_mode) and is_cluster_route_goal:
                        planner_state.current_route = None
                        planner_state.current_route_mode = "route"
                        planner_state.current_route_reason = "confirmed_target_route"
                        planner_state.current_route_details = {}
                    if current_goal_mode == "route":
                        route_false_visits += 1
            row = {
                "time_s": t_s + dt_s,
                "event": "goal_completed",
                "mode": current_goal_mode,
                "reason": current_goal_reason,
                "x": float(pos[0]),
                "y": float(pos[1]),
                "collected_delta": collected_delta,
                "goal_path_m": float(goal_path),
                "goal_time_s": float(goal_time),
                "empty_goal": collected_delta == 0,
                "expected_value": float(current_goal_expected_value),
            }
            row.update(current_goal_details)
            events.append(row)
            if np.linalg.norm(pos - np.array(config.world.depot, dtype=float)) <= config.platform.arrival_tolerance_m and bin_load_kg > 0:
                unload_events += 1
                events.append(
                    {
                        "time_s": t_s + dt_s,
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
                "wasted_time_to_empty_goals": wasted_time_to_empty_goals,
            }
        )

        t_s += dt_s

    if total_path_m >= config.platform.max_path_m and stop_reason != "done":
        stop_reason = "path_budget"

    residual_counts = true_count_map(field, grid.x_edges, grid.y_edges, include_collected=False)
    quality = map_quality(density_map, residual_counts)
    collected_count = int(field.collected.sum())
    collected_ratio = collected_count / max(1, config.world.n_debris)
    collected_mass_kg = float(field.masses_kg[field.collected].sum())
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
        "collected_mass_kg": collected_mass_kg,
        "collected_mass_per_meter": collected_mass_kg / max(1e-9, total_path_m),
        "path_length_m": total_path_m,
        "sim_time_s": t_s,
        "goal_count": goal_count,
        "evaluated_goal_count": evaluated_goal_count,
        "empty_goal_arrivals": empty_goal_arrivals,
        "empty_goal_arrivals_per_km": empty_goal_arrivals / max(1e-9, total_path_m / 1000.0),
        "wasted_path_to_empty_goals": wasted_path_to_empty_goals,
        "wasted_path_ratio": wasted_path_to_empty_goals / max(1e-9, total_path_m),
        "wasted_time_to_empty_goals": wasted_time_to_empty_goals,
        "wasted_time_ratio": wasted_time_to_empty_goals / max(1e-9, t_s),
        "goal_success_rate": goal_successes / max(1, evaluated_goal_count),
        "route_false_visits": route_false_visits,
        "capture_contacts": capture_contacts,
        "terminal_capture_attempts": terminal_capture_attempts,
        "successful_captures": successful_captures,
        "missed_capture_count": missed_capture_count,
        "missed_captures": missed_capture_count,
        "partial_contact_events": partial_contact_events,
        "throughput_limit_events": throughput_limit_events,
        "bin_full_events": bin_full_events,
        "collection_precision": successful_captures / max(1, terminal_capture_attempts),
        "pushed_away_events": pushed_away_events,
        "pushed_away_debris_count": int(np.count_nonzero(field.pushed_events)),
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
