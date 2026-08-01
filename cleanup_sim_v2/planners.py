from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import PlannerConfig, PlatformConfig, WorldConfig
from .mapping import DensityMap, entropy
from .targets import TargetQueue


@dataclass
class PlannerState:
    coverage_route: list[np.ndarray]
    coverage_index: int = 0
    active_goal: np.ndarray | None = None
    last_replan_t_s: float = -1e9
    greedy_suppressed: np.ndarray | None = None
    current_route: list[np.ndarray] | None = None


def make_coverage_route(world: WorldConfig, planner: PlannerConfig) -> list[np.ndarray]:
    ys = np.arange(planner.coverage_margin_m, world.height_m - planner.coverage_margin_m + 1e-9, planner.coverage_spacing_m)
    x_min = planner.coverage_margin_m
    x_max = world.width_m - planner.coverage_margin_m
    route: list[np.ndarray] = []
    for j, y in enumerate(ys):
        if j % 2 == 0:
            route.append(np.array([x_min, y], dtype=float))
            route.append(np.array([x_max, y], dtype=float))
        else:
            route.append(np.array([x_max, y], dtype=float))
            route.append(np.array([x_min, y], dtype=float))
    return route or [np.array(world.depot, dtype=float)]


def initial_state(world: WorldConfig, planner: PlannerConfig) -> PlannerState:
    return PlannerState(coverage_route=make_coverage_route(world, planner))


def next_coverage(state: PlannerState) -> np.ndarray:
    if state.coverage_index >= len(state.coverage_route):
        state.coverage_index = 0
    goal = state.coverage_route[state.coverage_index]
    state.coverage_index += 1
    return goal.copy()


def suppress_greedy_goal(state: PlannerState, density_map: DensityMap, pos: np.ndarray, radius_m: float) -> None:
    if state.greedy_suppressed is None or state.greedy_suppressed.shape != density_map.expected_count.shape:
        state.greedy_suppressed = np.zeros_like(density_map.expected_count, dtype=bool)
    dist = np.hypot(density_map.grid.xx - pos[0], density_map.grid.yy - pos[1])
    state.greedy_suppressed |= dist <= radius_m


def next_greedy(state: PlannerState, density_map: DensityMap, current: np.ndarray, platform: PlatformConfig) -> np.ndarray:
    score = density_map.expected_count.copy()
    if state.greedy_suppressed is not None and state.greedy_suppressed.shape == score.shape:
        score[state.greedy_suppressed] = -np.inf
    dist = np.hypot(density_map.grid.xx - current[0], density_map.grid.yy - current[1])
    score[dist <= max(platform.arrival_tolerance_m, platform.collection_width_m)] = -np.inf
    if not np.isfinite(score).any():
        state.greedy_suppressed = np.zeros_like(density_map.expected_count, dtype=bool)
        score = density_map.expected_count.copy()
    iy, ix = np.unravel_index(int(np.nanargmax(score)), score.shape)
    return np.array([density_map.grid.x_centers[ix], density_map.grid.y_centers[iy]], dtype=float)


def candidate_waypoints(world: WorldConfig, planner: PlannerConfig) -> np.ndarray:
    xs = np.arange(planner.coverage_margin_m, world.width_m - planner.coverage_margin_m + 1e-9, planner.candidate_spacing_m)
    ys = np.arange(planner.coverage_margin_m, world.height_m - planner.coverage_margin_m + 1e-9, planner.candidate_spacing_m)
    xx, yy = np.meshgrid(xs, ys, indexing="xy")
    return np.column_stack([xx.ravel(), yy.ravel()])


def next_active(current: np.ndarray, density_map: DensityMap, world: WorldConfig, planner: PlannerConfig) -> np.ndarray:
    candidates = candidate_waypoints(world, planner)
    occ = density_map.occupancy
    h = entropy(occ)
    scores = []
    for point in candidates:
        travel = float(np.linalg.norm(point - current))
        if travel <= max(2.0, 0.25 * planner.candidate_spacing_m):
            scores.append(-np.inf)
            continue
        dist_to_cells = np.hypot(density_map.grid.xx - point[0], density_map.grid.yy - point[1])
        local = dist_to_cells <= planner.candidate_spacing_m
        info = float(np.mean(h[local])) if np.any(local) else 0.0
        density = float(np.sum(density_map.expected_count[local])) if np.any(local) else 0.0
        scores.append(
            planner.active_entropy_weight * info
            + planner.active_density_weight * density
            - planner.active_distance_weight * travel
        )
    if not np.isfinite(scores).any():
        return next_greedy(PlannerState(coverage_route=[]), density_map, current, PlatformConfig())
    return candidates[int(np.argmax(scores))].astype(float)


def nearest_neighbor_route(start: np.ndarray, targets: list[np.ndarray], limit: int) -> list[np.ndarray]:
    remaining = [np.asarray(t, dtype=float).copy() for t in targets]
    route: list[np.ndarray] = []
    current = np.asarray(start, dtype=float)
    while remaining and len(route) < limit:
        distances = [float(np.linalg.norm(t - current)) for t in remaining]
        idx = int(np.argmin(distances))
        current = remaining.pop(idx)
        route.append(current.copy())
    return route


def choose_goal(
    t_s: float,
    current: np.ndarray,
    state: PlannerState,
    density_map: DensityMap,
    world: WorldConfig,
    platform: PlatformConfig,
    planner: PlannerConfig,
    targets: TargetQueue,
) -> tuple[np.ndarray, str]:
    if state.current_route:
        return state.current_route[0].copy(), "route"
    if planner.mode in {"coverage", "lawnmower_survey", "lawnmower_collect"}:
        return next_coverage(state), "coverage"
    if planner.mode == "greedy":
        return next_greedy(state, density_map, current, platform), "greedy"
    if planner.mode == "confirmed_route":
        confirmed = targets.confirmed_targets()
        if confirmed:
            state.current_route = nearest_neighbor_route(current, confirmed, planner.route_batch_size)
            if state.current_route:
                return state.current_route[0].copy(), "route"
        return next_coverage(state), "coverage"

    active_reached = state.active_goal is not None and np.linalg.norm(state.active_goal - current) <= platform.arrival_tolerance_m
    if state.active_goal is None or active_reached or t_s - state.last_replan_t_s >= planner.replan_interval_s:
        state.last_replan_t_s = t_s
        state.active_goal = next_active(current, density_map, world, planner)
    return state.active_goal.copy(), "active"


def pop_route_goal_if_arrived(state: PlannerState, pos: np.ndarray, tolerance_m: float, targets: TargetQueue) -> None:
    if not state.current_route:
        return
    if np.linalg.norm(state.current_route[0] - pos) <= tolerance_m:
        targets.remove_near(pos, tolerance_m * 2.5)
        state.current_route.pop(0)
