from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import PlannerConfig, PlatformConfig, WorldConfig
from .mapping import DensityMap, entropy
from .targets import TargetQueue
from .world import DebrisField


@dataclass
class PlannerState:
    coverage_route: list[np.ndarray]
    coverage_index: int = 0
    active_goal: np.ndarray | None = None
    last_replan_t_s: float = -1e9
    greedy_suppressed: np.ndarray | None = None
    current_route: list[np.ndarray] | None = None
    oracle_route: list[np.ndarray] | None = None


@dataclass(frozen=True)
class GoalDecision:
    point: np.ndarray
    mode: str
    reason: str
    expected_value: float


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


def _route_length(start: np.ndarray, route: list[np.ndarray]) -> float:
    if not route:
        return 0.0
    length = 0.0
    current = np.asarray(start, dtype=float)
    for point in route:
        length += float(np.linalg.norm(point - current))
        current = point
    return length


def two_opt_route(start: np.ndarray, route: list[np.ndarray], max_passes: int = 2) -> list[np.ndarray]:
    best = [np.asarray(point, dtype=float).copy() for point in route]
    if len(best) < 4:
        return best
    best_length = _route_length(start, best)
    for _ in range(max_passes):
        improved = False
        for i in range(len(best) - 2):
            for j in range(i + 2, len(best)):
                candidate = best[:i] + list(reversed(best[i:j])) + best[j:]
                candidate_length = _route_length(start, candidate)
                if candidate_length + 1e-9 < best_length:
                    best = candidate
                    best_length = candidate_length
                    improved = True
        if not improved:
            break
    return best


def _nearest_alive_debris(field: DebrisField, current: np.ndarray, use_initial_positions: bool) -> np.ndarray | None:
    alive = np.where(~field.collected)[0]
    if alive.size == 0:
        return None
    positions = field.initial_positions[alive] if use_initial_positions else field.positions[alive]
    idx = int(np.argmin(np.linalg.norm(positions - current, axis=1)))
    return positions[idx].astype(float).copy()


def _build_oracle_route(
    state: PlannerState,
    current: np.ndarray,
    field: DebrisField,
    planner: PlannerConfig,
    use_initial_positions: bool,
) -> list[np.ndarray]:
    if state.oracle_route:
        return state.oracle_route
    alive = np.where(~field.collected)[0]
    if alive.size == 0:
        state.oracle_route = []
        return state.oracle_route
    positions = field.initial_positions[alive] if use_initial_positions else field.positions[alive]
    raw_route = nearest_neighbor_route(current, [p for p in positions], max(1, planner.route_batch_size))
    state.oracle_route = two_opt_route(current, raw_route)
    return state.oracle_route


def choose_goal(
    t_s: float,
    current: np.ndarray,
    state: PlannerState,
    density_map: DensityMap,
    world: WorldConfig,
    platform: PlatformConfig,
    planner: PlannerConfig,
    targets: TargetQueue,
    field: DebrisField | None = None,
) -> GoalDecision:
    if state.current_route:
        return GoalDecision(state.current_route[0].copy(), "route", "confirmed_target_route", 1.0)
    if planner.mode == "oracle_current_physics" and field is not None:
        point = _nearest_alive_debris(field, current, use_initial_positions=False)
        if point is None:
            point = np.array(world.depot, dtype=float)
        return GoalDecision(point, "oracle", "nearest_current_true_debris", 1.0)
    if planner.mode == "oracle_perfect_static" and field is not None:
        route = _build_oracle_route(state, current, field, planner, use_initial_positions=True)
        point = route[0].copy() if route else np.array(world.depot, dtype=float)
        return GoalDecision(point, "oracle", "initial_truth_route", 1.0)
    if planner.mode == "oracle_route_heuristic" and field is not None:
        route = _build_oracle_route(state, current, field, planner, use_initial_positions=False)
        point = route[0].copy() if route else np.array(world.depot, dtype=float)
        return GoalDecision(point, "oracle", "current_truth_route_2opt", 1.0)
    if planner.mode in {"coverage", "lawnmower_survey", "lawnmower_collect"}:
        return GoalDecision(next_coverage(state), "coverage", planner.mode, 0.0)
    if planner.mode == "greedy":
        point = next_greedy(state, density_map, current, platform)
        iy = int(np.argmin(np.abs(density_map.grid.y_centers - point[1])))
        ix = int(np.argmin(np.abs(density_map.grid.x_centers - point[0])))
        return GoalDecision(point, "greedy", "max_expected_count", float(density_map.expected_count[iy, ix]))
    if planner.mode == "confirmed_route":
        confirmed = targets.confirmed_targets(t_s)
        if confirmed:
            state.current_route = nearest_neighbor_route(current, confirmed, planner.route_batch_size)
            if state.current_route:
                return GoalDecision(state.current_route[0].copy(), "route", "confirmed_target_route", 1.0)
        return GoalDecision(next_coverage(state), "coverage", "no_confirmed_targets", 0.0)

    active_reached = state.active_goal is not None and np.linalg.norm(state.active_goal - current) <= platform.arrival_tolerance_m
    if state.active_goal is None or active_reached or t_s - state.last_replan_t_s >= planner.replan_interval_s:
        state.last_replan_t_s = t_s
        state.active_goal = next_active(current, density_map, world, planner)
    return GoalDecision(state.active_goal.copy(), "active", "active_entropy_density_score", 0.0)


def pop_route_goal_if_arrived(state: PlannerState, pos: np.ndarray, tolerance_m: float, targets: TargetQueue) -> None:
    if state.current_route and np.linalg.norm(state.current_route[0] - pos) <= tolerance_m:
        targets.remove_near(pos, tolerance_m * 2.5)
        state.current_route.pop(0)
    if state.oracle_route and np.linalg.norm(state.oracle_route[0] - pos) <= tolerance_m:
        state.oracle_route.pop(0)
