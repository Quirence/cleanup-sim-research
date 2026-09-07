from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .collection import CaptureEvent, collect_in_aperture
from .config import RunConfig
from .hydrodynamics import ambient_velocity, drift_debris
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
        "confirmed_target_approach",
        "provisional_target_approach",
        "density_approach",
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


def _diagnostic_radius_m(config: RunConfig) -> float:
    return max(12.0, 0.75 * config.planner.candidate_spacing_m)


def _true_local_stats(field: DebrisField, point: np.ndarray, radius_m: float) -> tuple[int, float, float]:
    alive = np.where(~field.collected)[0]
    if alive.size == 0:
        return 0, 0.0, float("nan")
    distances = np.linalg.norm(field.positions[alive] - point, axis=1)
    local = distances <= radius_m
    local_ids = alive[local]
    nearest = float(np.min(distances)) if distances.size else float("nan")
    mass = float(field.masses_kg[local_ids].sum()) if local_ids.size else 0.0
    return int(local_ids.size), mass, nearest


def _true_swept_count(field: DebrisField, start: np.ndarray, goal: np.ndarray, platform) -> int:
    alive = np.where(~field.collected)[0]
    if alive.size == 0:
        return 0
    direction = goal - start
    dist = float(np.linalg.norm(direction))
    if dist <= 1e-9:
        return 0
    direction = direction / dist
    rel = field.positions[alive] - start
    along = rel @ direction
    lateral = np.abs(rel[:, 0] * direction[1] - rel[:, 1] * direction[0])
    mask = (
        (along >= -0.15 * platform.collection_length_m)
        & (along <= dist + platform.collection_length_m)
        & (lateral <= 0.5 * platform.collection_width_m)
    )
    return int(np.count_nonzero(mask))


def _candidate_group(goal_mode: str, candidate_type: object) -> str:
    kind = "" if candidate_type is None else str(candidate_type)
    if goal_mode in {"greedy", "route", "oracle", "coverage", "return"}:
        return goal_mode
    if kind.endswith("_refine"):
        return "refinement"
    if kind.startswith("confirmed_target") or kind.startswith("provisional_target"):
        return "target"
    if kind.startswith("density"):
        return "density"
    if kind.startswith("entropy"):
        return "entropy"
    if "coverage" in kind:
        return "coverage"
    if kind == "fallback":
        return "fallback"
    return "other"


def _retarget_track_policy(
    config: RunConfig,
    old_group: str,
    old_track_id: int,
    old_goal: np.ndarray,
    new_goal: np.ndarray,
) -> dict[str, float | bool]:
    region_distance_m = float(np.linalg.norm(new_goal - old_goal))
    same_region = region_distance_m <= config.planner.belief_goal_retarget_region_radius_m
    drift_speed_mps = float(np.linalg.norm(ambient_velocity(config.hydro)))
    drift_sensitive = drift_speed_mps >= config.planner.belief_goal_retarget_drift_speed_threshold_mps
    same_track_required = bool(
        old_group in {"target", "refinement"}
        and old_track_id > 0
        and (
            config.planner.belief_goal_retarget_require_same_track
            or (
                config.planner.belief_goal_retarget_region_adaptive
                and drift_sensitive
                and not same_region
            )
            or (
                config.planner.belief_goal_retarget_drift_switch
                and drift_sensitive
            )
        )
    )
    return {
        "same_track_required": same_track_required,
        "same_region": bool(same_region),
        "retarget_region_distance_m": region_distance_m,
        "drift_speed_mps": drift_speed_mps,
        "drift_sensitive": bool(drift_sensitive),
        "drift_switch": bool(config.planner.belief_goal_retarget_drift_switch),
    }


def _append_capture_event(
    events: list[dict],
    cap: CaptureEvent,
    t_s: float,
    mode: str,
    bin_load_kg: float,
    path_m: float,
) -> None:
    row = {
        "time_s": t_s,
        "path_m": path_m,
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
    current_goal_last_retarget_t_s = -1e9
    current_goal_retarget_count = 0
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
    goal_retarget_count = 0
    diagnostic_radius_m = _diagnostic_radius_m(config)
    local_opportunity_threshold = max(3, int(0.02 * config.world.n_debris))
    first_detection_path_m: float | None = None
    first_collection_path_m: float | None = None
    goal_group_counts: dict[str, int] = {}
    goal_group_empty_counts: dict[str, int] = {}
    goal_group_success_counts: dict[str, int] = {}
    goal_group_path_m: dict[str, float] = {}
    goal_group_wasted_path_m: dict[str, float] = {}
    goal_group_collected_delta: dict[str, int] = {}
    density_empty_goal_count = 0
    density_goal_count = 0
    target_goal_count = 0
    target_empty_goal_count = 0
    refinement_path_m = 0.0
    true_positive_goal_count = 0
    true_empty_goal_count = 0
    missed_local_opportunity_count = 0
    missed_local_opportunity_path_m = 0.0
    post_success_departures_from_rich_area = 0
    previous_goal_local_remaining_count = 0
    previous_goal_had_local_opportunity = False
    previous_goal_position: np.ndarray | None = None

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
                if not det.is_false and first_detection_path_m is None:
                    first_detection_path_m = total_path_m
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
            if previous_goal_had_local_opportunity and previous_goal_position is not None:
                residual_distance = float(np.linalg.norm(pos - previous_goal_position))
                previous_local_remaining_for_row = previous_goal_local_remaining_count
            else:
                residual_distance = 0.0
                previous_local_remaining_for_row = 0
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
            current_goal_last_retarget_t_s = t_s
            current_goal_retarget_count = 0
            current_goal_start_collected = int(field.collected.sum())
            local_count, local_mass, nearest_true_m = _true_local_stats(field, current_goal, diagnostic_radius_m)
            true_swept_count = _true_swept_count(field, pos, current_goal, config.platform)
            candidate_group = _candidate_group(current_goal_mode, current_goal_details.get("candidate_type"))
            if previous_goal_had_local_opportunity and previous_goal_position is not None:
                next_goal_distance_from_rich_area = float(np.linalg.norm(current_goal - previous_goal_position))
                if next_goal_distance_from_rich_area > diagnostic_radius_m:
                    post_success_departures_from_rich_area += 1
                    missed_local_opportunity_path_m += next_goal_distance_from_rich_area
            else:
                next_goal_distance_from_rich_area = 0.0
            previous_goal_had_local_opportunity = False
            previous_goal_position = None
            previous_goal_local_remaining_count = 0
            row = {
                "time_s": t_s,
                "path_m": total_path_m,
                "event": "goal_started",
                "mode": current_goal_mode,
                "reason": current_goal_reason,
                "candidate_group": candidate_group,
                "x": float(current_goal[0]),
                "y": float(current_goal[1]),
                "distance_m": float(np.linalg.norm(current_goal - pos)),
                "map_value": _grid_value(density_map, current_goal),
                "expected_value": float(current_goal_expected_value),
                "true_local_count": local_count,
                "true_local_mass_kg": local_mass,
                "nearest_true_debris_m": nearest_true_m,
                "true_swept_count": true_swept_count,
                "diagnostic_radius_m": diagnostic_radius_m,
                "previous_goal_local_remaining_count": previous_local_remaining_for_row,
                "next_goal_distance_from_rich_area_m": next_goal_distance_from_rich_area,
                "residual_distance_from_previous_goal_m": residual_distance,
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
                        "path_m": total_path_m,
                        "event": "goal_updated",
                        "mode": current_goal_mode,
                        "reason": current_goal_reason,
                        "x": float(current_goal[0]),
                        "y": float(current_goal[1]),
                        "distance_m": float(np.linalg.norm(current_goal - pos)),
                        "expected_value": float(current_goal_expected_value),
                    }
                )
        elif (
            config.planner.belief_goal_retarget_enabled
            and _is_belief_goal_mode(current_goal_mode)
            and current_goal is not None
            and current_goal_arrived_time is None
            and current_goal_retarget_count < config.planner.belief_goal_retarget_max_per_goal
            and t_s - current_goal_last_retarget_t_s >= config.planner.belief_goal_retarget_interval_s
        ):
            old_goal = current_goal.copy()
            old_candidate_type = str(current_goal_details.get("candidate_type", ""))
            old_track_id = int(float(current_goal_details.get("target_track_id", 0) or 0))
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
            new_candidate_type = str(decision.details.get("candidate_type", ""))
            new_track_id = int(float(decision.details.get("target_track_id", 0) or 0))
            old_group = _candidate_group(current_goal_mode, old_candidate_type)
            new_group = _candidate_group(decision.mode, new_candidate_type)
            shift_m = float(np.linalg.norm(decision.point - old_goal))
            old_remaining_m = float(np.linalg.norm(old_goal - pos))
            new_remaining_m = float(np.linalg.norm(decision.point - pos))
            score_floor = current_goal_expected_value - config.planner.belief_goal_retarget_score_tolerance
            retarget_policy = _retarget_track_policy(config, old_group, old_track_id, old_goal, decision.point)
            same_track_required = bool(retarget_policy["same_track_required"])
            same_track_ok = not same_track_required or new_track_id == old_track_id
            should_retarget = (
                decision.mode == current_goal_mode
                and old_group == new_group
                and old_candidate_type == new_candidate_type
                and same_track_ok
                and config.planner.belief_goal_retarget_min_shift_m <= shift_m <= config.planner.belief_goal_retarget_max_shift_m
                and new_remaining_m <= old_remaining_m + config.planner.belief_goal_retarget_max_extra_travel_m
                and decision.expected_value >= score_floor
            )
            current_goal_last_retarget_t_s = t_s
            if should_retarget:
                current_goal = decision.point
                current_goal_reason = f"{current_goal_reason}|retarget"
                current_goal_expected_value = decision.expected_value
                current_goal_details = dict(decision.details)
                current_goal_arrived_time = None
                goal_retarget_count += 1
                current_goal_retarget_count += 1
                events.append(
                    {
                        "time_s": t_s,
                        "path_m": total_path_m,
                        "event": "goal_retargeted",
                        "mode": current_goal_mode,
                        "reason": current_goal_reason,
                        "candidate_type": new_candidate_type,
                        "old_target_track_id": old_track_id,
                        "target_track_id": new_track_id,
                        "same_track_required": bool(same_track_required),
                        "same_track_ok": bool(same_track_ok),
                        "region_adaptive": bool(config.planner.belief_goal_retarget_region_adaptive),
                        "same_region": bool(retarget_policy["same_region"]),
                        "retarget_region_distance_m": float(retarget_policy["retarget_region_distance_m"]),
                        "drift_speed_mps": float(retarget_policy["drift_speed_mps"]),
                        "drift_sensitive": bool(retarget_policy["drift_sensitive"]),
                        "drift_switch": bool(retarget_policy["drift_switch"]),
                        "old_x": float(old_goal[0]),
                        "old_y": float(old_goal[1]),
                        "x": float(current_goal[0]),
                        "y": float(current_goal[1]),
                        "shift_m": shift_m,
                        "old_remaining_m": old_remaining_m,
                        "new_remaining_m": new_remaining_m,
                        "expected_value": float(current_goal_expected_value),
                        "retarget_count_for_goal": current_goal_retarget_count,
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
                if cap.success and first_collection_path_m is None:
                    first_collection_path_m = total_path_m
                _append_capture_event(events, cap, sub_t_s, current_goal_mode, bin_load_kg, total_path_m)

            arrived = arrived or sub_arrived
            if np.all(field.collected) or total_path_m >= config.platform.max_path_m:
                break

        if np.all(field.collected):
            stop_reason = "done"
            events.append(
                {
                    "time_s": t_s,
                    "path_m": total_path_m,
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
            current_goal_last_retarget_t_s = t_s + dt_s
            current_goal_retarget_count = 0
            current_goal_start_collected = int(field.collected.sum())
            events.append(
                {
                    "time_s": t_s + dt_s,
                    "path_m": total_path_m,
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
            candidate_group = _candidate_group(current_goal_mode, candidate_type)
            local_remaining_count, local_remaining_mass, nearest_remaining_m = _true_local_stats(
                field,
                current_goal,
                diagnostic_radius_m,
            )
            true_swept_remaining_count = _true_swept_count(field, pos, current_goal, config.platform)
            is_refinement_goal = (
                _is_belief_goal_mode(current_goal_mode)
                and str(candidate_type).endswith("_refine")
            )
            is_cluster_route_goal = candidate_type == "cluster_route_transect"
            is_transect_goal = candidate_type in {
                "confirmed_target_transect",
                "provisional_target_transect",
                "density_transect",
                "confirmed_target_approach",
                "provisional_target_approach",
                "density_approach",
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
                goal_group_counts[candidate_group] = goal_group_counts.get(candidate_group, 0) + 1
                goal_group_path_m[candidate_group] = goal_group_path_m.get(candidate_group, 0.0) + goal_path
                goal_group_collected_delta[candidate_group] = (
                    goal_group_collected_delta.get(candidate_group, 0) + collected_delta
                )
                if candidate_group == "density":
                    density_goal_count += 1
                if candidate_group == "target":
                    target_goal_count += 1
                if local_remaining_count > 0 or collected_delta > 0:
                    true_positive_goal_count += 1
                else:
                    true_empty_goal_count += 1
                if collected_delta > 0:
                    goal_successes += 1
                    goal_group_success_counts[candidate_group] = goal_group_success_counts.get(candidate_group, 0) + 1
                    if local_remaining_count >= local_opportunity_threshold:
                        missed_local_opportunity_count += 1
                        previous_goal_had_local_opportunity = True
                        previous_goal_position = current_goal.copy()
                        previous_goal_local_remaining_count = local_remaining_count
                    else:
                        previous_goal_had_local_opportunity = False
                        previous_goal_position = None
                        previous_goal_local_remaining_count = 0
                    if _is_belief_goal_mode(current_goal_mode) and is_transect_goal:
                        target_queue.remove_near(current_goal, empty_suppression_radius)
                        if not is_cluster_route_goal:
                            planner_state.current_route = None
                            planner_state.current_route_mode = "route"
                            planner_state.current_route_reason = "confirmed_target_route"
                            planner_state.current_route_details = {}
                else:
                    empty_goal_arrivals += 1
                    goal_group_empty_counts[candidate_group] = goal_group_empty_counts.get(candidate_group, 0) + 1
                    goal_group_wasted_path_m[candidate_group] = (
                        goal_group_wasted_path_m.get(candidate_group, 0.0) + goal_path
                    )
                    if candidate_group == "density":
                        density_empty_goal_count += 1
                    if candidate_group == "target":
                        target_empty_goal_count += 1
                    wasted_path_to_empty_goals += goal_path
                    wasted_time_to_empty_goals += goal_time
                    previous_goal_had_local_opportunity = False
                    previous_goal_position = None
                    previous_goal_local_remaining_count = 0
                    target_queue.suppress_near(current_goal, t_s + dt_s, empty_suppression_radius)
                    if _is_belief_goal_mode(current_goal_mode) and is_cluster_route_goal:
                        planner_state.current_route = None
                        planner_state.current_route_mode = "route"
                        planner_state.current_route_reason = "confirmed_target_route"
                        planner_state.current_route_details = {}
                    if current_goal_mode == "route":
                        route_false_visits += 1
            elif is_refinement_goal:
                refinement_path_m += goal_path
            row = {
                "time_s": t_s + dt_s,
                "path_m": total_path_m,
                "event": "goal_completed",
                "mode": current_goal_mode,
                "reason": current_goal_reason,
                "candidate_group": candidate_group,
                "x": float(pos[0]),
                "y": float(pos[1]),
                "collected_delta": collected_delta,
                "goal_path_m": float(goal_path),
                "goal_time_s": float(goal_time),
                "empty_goal": collected_delta == 0,
                "expected_value": float(current_goal_expected_value),
                "true_local_remaining_count": local_remaining_count,
                "true_local_remaining_mass_kg": local_remaining_mass,
                "nearest_remaining_debris_m": nearest_remaining_m,
                "true_swept_remaining_count": true_swept_remaining_count,
                "missed_local_opportunity": bool(collected_delta > 0 and local_remaining_count >= local_opportunity_threshold),
                "local_opportunity_threshold": local_opportunity_threshold,
            }
            row.update(current_goal_details)
            events.append(row)
            if np.linalg.norm(pos - np.array(config.world.depot, dtype=float)) <= config.platform.arrival_tolerance_m and bin_load_kg > 0:
                unload_events += 1
                events.append(
                    {
                        "time_s": t_s + dt_s,
                        "path_m": total_path_m,
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
    density_wasted_path = goal_group_wasted_path_m.get("density", 0.0)
    target_wasted_path = goal_group_wasted_path_m.get("target", 0.0)
    coverage_wasted_path = goal_group_wasted_path_m.get("coverage", 0.0)
    density_collected_delta = goal_group_collected_delta.get("density", 0)
    target_collected_delta = goal_group_collected_delta.get("target", 0)
    coverage_collected_delta = goal_group_collected_delta.get("coverage", 0)
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
        "first_detection_path_m": float(first_detection_path_m) if first_detection_path_m is not None else float("nan"),
        "first_collection_path_m": float(first_collection_path_m) if first_collection_path_m is not None else float("nan"),
        "empty_goal_arrivals": empty_goal_arrivals,
        "empty_goal_arrivals_per_km": empty_goal_arrivals / max(1e-9, total_path_m / 1000.0),
        "wasted_path_to_empty_goals": wasted_path_to_empty_goals,
        "wasted_path_ratio": wasted_path_to_empty_goals / max(1e-9, total_path_m),
        "wasted_time_to_empty_goals": wasted_time_to_empty_goals,
        "wasted_time_ratio": wasted_time_to_empty_goals / max(1e-9, t_s),
        "goal_success_rate": goal_successes / max(1, evaluated_goal_count),
        "true_positive_goal_count": true_positive_goal_count,
        "true_empty_goal_count": true_empty_goal_count,
        "true_empty_goal_rate": true_empty_goal_count / max(1, evaluated_goal_count),
        "density_goal_count": density_goal_count,
        "density_empty_goal_count": density_empty_goal_count,
        "density_empty_goal_rate": density_empty_goal_count / max(1, density_goal_count),
        "density_wasted_path_m": density_wasted_path,
        "density_wasted_path_ratio": density_wasted_path / max(1e-9, total_path_m),
        "density_collected_delta": density_collected_delta,
        "target_goal_count": target_goal_count,
        "target_empty_goal_count": target_empty_goal_count,
        "target_empty_goal_rate": target_empty_goal_count / max(1, target_goal_count),
        "target_wasted_path_m": target_wasted_path,
        "target_wasted_path_ratio": target_wasted_path / max(1e-9, total_path_m),
        "target_collected_delta": target_collected_delta,
        "coverage_wasted_path_m": coverage_wasted_path,
        "coverage_wasted_path_ratio": coverage_wasted_path / max(1e-9, total_path_m),
        "coverage_collected_delta": coverage_collected_delta,
        "refinement_path_m": refinement_path_m,
        "refinement_path_ratio": refinement_path_m / max(1e-9, total_path_m),
        "missed_local_opportunity_count": missed_local_opportunity_count,
        "missed_local_opportunity_rate": missed_local_opportunity_count / max(1, goal_successes),
        "post_success_departures_from_rich_area": post_success_departures_from_rich_area,
        "missed_local_opportunity_path_m": missed_local_opportunity_path_m,
        "missed_local_opportunity_path_ratio": missed_local_opportunity_path_m / max(1e-9, total_path_m),
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
        "goal_retarget_count": goal_retarget_count,
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
