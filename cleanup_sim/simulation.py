from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import RunConfig
from .mapping import init_probability_map, make_grid
from .metrics import TimeSeries, path_length, summarize_run
from .planners import (
    PlannerState,
    choose_next_goal,
    lawnmower_route,
    pop_arrived_route_goal,
    suppress_greedy_region,
    update_detected_targets,
)
from .sensors import apply_fusion_update
from .targets import TargetQueue
from .world import DebrisField, make_debris_field, true_occupancy


@dataclass
class SimulationResult:
    config: RunConfig
    field: DebrisField
    path: np.ndarray
    belief: np.ndarray
    true_occ: np.ndarray
    residual_true_occ: np.ndarray
    events: pd.DataFrame
    series: pd.DataFrame
    summary: dict


def _collect_nearby(field: DebrisField, pos: np.ndarray, radius: float, bin_load: float) -> tuple[list[dict], float]:
    events = []
    remaining = np.where(~field.collected)[0]
    for i in remaining:
        if np.linalg.norm(field.positions[i] - pos) <= radius:
            field.collected[i] = True
            bin_load += float(field.masses[i])
            events.append({
                "event": "collect",
                "debris_id": int(i),
                "x": float(field.positions[i, 0]),
                "y": float(field.positions[i, 1]),
                "mass_kg": float(field.masses[i]),
                "type": str(field.types[i]),
                "bin_load_kg": float(bin_load),
            })
    return events, bin_load


def _step_toward(pos: np.ndarray, goal: np.ndarray, speed: float, dt: float) -> tuple[np.ndarray, float, bool]:
    vec = goal - pos
    dist = float(np.linalg.norm(vec))
    if dist < 1e-9:
        return pos.copy(), 0.0, True
    step = min(speed * dt, dist)
    return pos + vec * (step / dist), step, step >= dist - 1e-9


def _collected_near_goal(collected_events: list[dict], goal: np.ndarray | None, radius_m: float) -> bool:
    if goal is None:
        return False
    for event in collected_events:
        event_pos = np.array([event["x"], event["y"]], dtype=float)
        if np.linalg.norm(event_pos - goal) <= radius_m:
            return True
    return False


def run_simulation(config: RunConfig) -> SimulationResult:
    rng = np.random.default_rng(config.seed)
    field = make_debris_field(rng, config.world)
    grid = make_grid(config.world, config.grid)
    prob_map = init_probability_map(grid, config.grid)
    true_occ = true_occupancy(field, grid.x_edges, grid.y_edges)

    state = PlannerState(coverage_route=lawnmower_route(config.world, config.planner))
    target_queue = TargetQueue(
        confirm_prob=config.planner.detected_confirm_prob,
        confirm_hits=config.planner.target_confirm_hits,
        nms_radius_m=config.planner.detected_nms_radius_m,
        min_sensor_types=config.planner.target_min_sensor_types,
    )
    pos = np.array(config.world.depot, dtype=float)
    heading = 0.0
    path = [pos.copy()]
    events: list[dict] = []
    false_visits = 0
    target_confirmed = 0
    target_route_attempts = 0
    target_visit_successes = 0
    target_visit_false = 0
    bin_load = 0.0
    current_goal: np.ndarray | None = None
    current_planner_mode = "init"
    route_goal_collected = False
    total_path_m = 0.0
    last_sensor_update_t = -1e9
    ts = TimeSeries(time_s=[], path_m=[], collected=[], false_visits=[], planner_mode=[])
    stop_reason = "time_budget"

    t = 0.0
    while t <= config.robot.tmax_s:
        if t - last_sensor_update_t >= config.robot.sensor_period_s:
            last_sensor_update_t = t
            detections = apply_fusion_update(rng, prob_map, field, np.array([pos[0], pos[1], heading]), config.fusion)
            confirmations = update_detected_targets(target_queue, detections, config.planner, config.world, t)
            for track in confirmations:
                target_confirmed += 1
                events.append({
                    "time_s": t,
                    "event": "target_confirmed",
                    "x": float(track.position[0]),
                    "y": float(track.position[1]),
                    "confidence": float(track.confidence),
                    "hits": int(track.hits),
                })
            for det in detections:
                events.append({
                    "time_s": t,
                    "event": "detect",
                    "sensor": det.sensor,
                    "x": float(det.position[0]),
                    "y": float(det.position[1]),
                    "confidence": det.confidence,
                    "source_id": det.source_index,
                })

        collected_events, bin_load = _collect_nearby(field, pos, config.robot.collect_radius_m, bin_load)
        collected_this_tick = len(collected_events)
        if current_planner_mode == "route" and _collected_near_goal(collected_events, current_goal, config.robot.collect_radius_m):
            route_goal_collected = True
        for event in collected_events:
            event["time_s"] = t
            events.append(event)

        if np.all(field.collected):
            events.append({"time_s": t, "event": "done", "x": float(pos[0]), "y": float(pos[1])})
            stop_reason = "done"
            break

        if bin_load >= config.robot.bin_capacity_kg * config.robot.return_ratio:
            current_goal = np.array(config.world.depot, dtype=float)
            current_planner_mode = "return"

        if current_goal is None or np.linalg.norm(current_goal - pos) <= config.robot.arrival_tolerance_m:
            arrived_goal = current_goal is not None and np.linalg.norm(current_goal - pos) <= config.robot.arrival_tolerance_m
            arrived_route_goal = arrived_goal and current_planner_mode == "route"
            if arrived_goal and current_planner_mode == "greedy":
                suppress_greedy_region(state, prob_map, current_goal, config.robot.collect_radius_m)
            if current_goal is not None and np.linalg.norm(current_goal - pos) <= config.robot.collect_radius_m:
                collected_events, bin_load = _collect_nearby(field, pos, config.robot.collect_radius_m, bin_load)
                collected_this_tick += len(collected_events)
                if current_planner_mode == "route" and _collected_near_goal(collected_events, current_goal, config.robot.collect_radius_m):
                    route_goal_collected = True
                for event in collected_events:
                    event["time_s"] = t
                    events.append(event)
                if arrived_route_goal:
                    target_route_attempts += 1
                    if collected_this_tick > 0 or route_goal_collected:
                        target_visit_successes += 1
                        target_queue.remove_near(pos, config.robot.collect_radius_m)
                        events.append({"time_s": t, "event": "target_visit_success", "x": float(pos[0]), "y": float(pos[1])})
                    else:
                        target_visit_false += 1
                        false_visits = target_visit_false
                        target_queue.suppress_near(pos, config.planner.target_false_suppress_radius_m)
                        events.append({"time_s": t, "event": "target_visit_false", "x": float(pos[0]), "y": float(pos[1])})
            if np.linalg.norm(pos - np.array(config.world.depot)) <= config.robot.arrival_tolerance_m and bin_load > 0:
                events.append({"time_s": t, "event": "unload", "x": float(pos[0]), "y": float(pos[1]), "bin_load_kg": bin_load})
                bin_load = 0.0
            pop_arrived_route_goal(
                state,
                pos,
                config.robot.arrival_tolerance_m,
                target_queue=target_queue,
                remove_radius_m=config.robot.collect_radius_m,
            )
            current_goal, current_planner_mode = choose_next_goal(
                t=t,
                current=pos,
                heading=heading,
                state=state,
                prob_map=prob_map,
                world=config.world,
                robot=config.robot,
                planner=config.planner,
                fusion=config.fusion,
                target_queue=target_queue,
            )
            if current_planner_mode == "route":
                route_goal_collected = False
                events.append({
                    "time_s": t,
                    "event": "target_routed",
                    "x": float(current_goal[0]),
                    "y": float(current_goal[1]),
                })
            else:
                route_goal_collected = False

        new_pos, step_m, _ = _step_toward(pos, current_goal, config.robot.speed_mps, config.robot.dt_s)
        if step_m > 0:
            heading = float(np.arctan2(new_pos[1] - pos[1], new_pos[0] - pos[0]))
        pos = new_pos
        path.append(pos.copy())
        total_path_m += step_m
        t += config.robot.dt_s

        ts.time_s.append(t)
        ts.path_m.append(total_path_m)
        ts.collected.append(int(field.collected.sum()))
        ts.false_visits.append(false_visits)
        ts.planner_mode.append(current_planner_mode)

        if total_path_m >= config.planner.max_path_m:
            stop_reason = "path_budget"
            events.append({"time_s": t, "event": "path_budget", "x": float(pos[0]), "y": float(pos[1])})
            break

    path_arr = np.asarray(path)
    residual_true_occ = true_occupancy(field, grid.x_edges, grid.y_edges, include_collected=False)
    events_df = pd.DataFrame(events)
    series_df = pd.DataFrame({
        "time_s": ts.time_s,
        "path_m": ts.path_m,
        "collected": ts.collected,
        "collected_ratio": np.array(ts.collected) / max(1, config.world.n_debris),
        "false_visits": ts.false_visits,
        "planner_mode": ts.planner_mode,
    })
    unloads = int((events_df["event"] == "unload").sum()) if not events_df.empty and "event" in events_df else 0
    summary = summarize_run(
        scenario=config.scenario,
        mode=config.planner.mode,
        seed=config.seed,
        total_debris=config.world.n_debris,
        collected_count=int(field.collected.sum()),
        collected_mass_kg=float(field.masses[field.collected].sum()),
        total_mass_kg=float(field.masses.sum()),
        path_m=path_length(path_arr),
        path_budget_m=config.planner.max_path_m,
        sim_time_s=float(t),
        unload_events=unloads,
        false_visits=false_visits,
        stop_reason=stop_reason,
        target_confirmed=target_confirmed,
        target_route_attempts=target_route_attempts,
        target_visit_successes=target_visit_successes,
        target_visit_false=target_visit_false,
        series=ts,
        belief=prob_map.belief,
        true_occ=true_occ,
        residual_true_occ=residual_true_occ,
    )
    return SimulationResult(
        config=config,
        field=field,
        path=path_arr,
        belief=prob_map.belief.copy(),
        true_occ=true_occ,
        residual_true_occ=residual_true_occ,
        events=events_df,
        series=series_df,
        summary=summary,
    )
