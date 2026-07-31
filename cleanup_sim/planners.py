from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import PlannerConfig, RobotConfig, WorldConfig
from .hybrid import HybridDecision, choose_hybrid_mode
from .mapping import ProbabilityMap, entropy
from .sensors import Detection, visible_mask
from .targets import TargetQueue, TargetTrack


@dataclass
class PlannerState:
    coverage_route: list[np.ndarray]
    coverage_index: int = 0
    current_route: list[np.ndarray] | None = None
    last_replan_t: float = -1e9
    greedy_suppressed_mask: np.ndarray | None = None
    active_goal: np.ndarray | None = None

    def __post_init__(self) -> None:
        if self.current_route is None:
            self.current_route = []


def lawnmower_route(world: WorldConfig, planner: PlannerConfig) -> list[np.ndarray]:
    xs = np.arange(planner.coverage_margin_m, world.width - planner.coverage_margin_m + 1e-9, planner.coverage_spacing_m)
    route: list[np.ndarray] = []
    direction = 1
    for x in xs:
        y0 = planner.coverage_margin_m if direction > 0 else world.height - planner.coverage_margin_m
        y1 = world.height - planner.coverage_margin_m if direction > 0 else planner.coverage_margin_m
        route.append(np.array([x, y0], dtype=float))
        route.append(np.array([x, y1], dtype=float))
        direction *= -1
    route.append(np.array(world.depot, dtype=float))
    return route


def candidate_waypoints(world: WorldConfig, planner: PlannerConfig) -> np.ndarray:
    xs = np.arange(planner.coverage_margin_m, world.width - planner.coverage_margin_m + 1e-9, planner.candidate_spacing_m)
    ys = np.arange(planner.coverage_margin_m, world.height - planner.coverage_margin_m + 1e-9, planner.candidate_spacing_m)
    xx, yy = np.meshgrid(xs, ys, indexing="xy")
    return np.column_stack([xx.ravel(), yy.ravel()])


def update_detected_targets(
    target_queue: TargetQueue,
    detections: list[Detection],
    planner: PlannerConfig,
    world: WorldConfig,
    t: float,
) -> list[TargetTrack]:
    confirmations = target_queue.add_detections(detections, t=t, world=world)
    target_queue.expire_stale(t=t, stale_after_s=planner.target_stale_after_s)
    return confirmations


def nearest_neighbor_route(start: np.ndarray, targets: list[np.ndarray], limit: int | None = None) -> list[np.ndarray]:
    if not targets:
        return []
    unused = [np.array(t, dtype=float) for t in targets]
    cur = start.copy()
    route: list[np.ndarray] = []
    while unused and (limit is None or len(route) < limit):
        d = np.array([np.linalg.norm(t - cur) for t in unused])
        j = int(np.argmin(d))
        route.append(unused.pop(j))
        cur = route[-1]
    return route


def next_lawnmower(state: PlannerState) -> np.ndarray:
    if state.coverage_index >= len(state.coverage_route):
        state.coverage_index = 0
    target = state.coverage_route[state.coverage_index]
    state.coverage_index += 1
    return target


def suppress_greedy_region(
    state: PlannerState,
    prob_map: ProbabilityMap,
    position: np.ndarray,
    radius_m: float,
) -> None:
    if state.greedy_suppressed_mask is None or state.greedy_suppressed_mask.shape != prob_map.belief.shape:
        state.greedy_suppressed_mask = np.zeros_like(prob_map.belief, dtype=bool)
    distance = np.hypot(prob_map.grid.xx - position[0], prob_map.grid.yy - position[1])
    state.greedy_suppressed_mask |= distance <= radius_m


def next_greedy(
    prob_map: ProbabilityMap,
    current: np.ndarray,
    state: PlannerState,
    exclude_radius_m: float,
) -> np.ndarray:
    scores = prob_map.belief.copy()
    if state.greedy_suppressed_mask is not None and state.greedy_suppressed_mask.shape == scores.shape:
        scores[state.greedy_suppressed_mask] = -np.inf
    local_distance = np.hypot(prob_map.grid.xx - current[0], prob_map.grid.yy - current[1])
    scores[local_distance <= exclude_radius_m] = -np.inf
    if not np.isfinite(scores).any():
        state.greedy_suppressed_mask = np.zeros_like(prob_map.belief, dtype=bool)
        scores = prob_map.belief.copy()
        scores[local_distance <= exclude_radius_m] = -np.inf
    if not np.isfinite(scores).any():
        scores = prob_map.belief
    iy, ix = np.unravel_index(int(np.argmax(scores)), scores.shape)
    return np.array([prob_map.grid.x_centers[ix], prob_map.grid.y_centers[iy]], dtype=float)


def _score_candidate(
    point: np.ndarray,
    current: np.ndarray,
    heading: float,
    prob_map: ProbabilityMap,
    planner: PlannerConfig,
    fusion_sensor,
) -> float:
    target_heading = np.arctan2(point[1] - current[1], point[0] - current[0])
    pose = np.array([point[0], point[1], target_heading if np.isfinite(target_heading) else heading], dtype=float)
    mask, _, _ = visible_mask(prob_map.grid, pose, fusion_sensor)
    if not np.any(mask):
        return -1e9
    b = prob_map.belief
    h = entropy(b)
    candidate = (b > planner.active_b_low) & (b < planner.active_b_high)
    entropy_value = float(np.sum(h[mask]))
    candidate_value = float(np.sum(candidate[mask]))
    probability_value = float(np.sum(b[mask]))
    local_dist = np.hypot(prob_map.grid.xx - point[0], prob_map.grid.yy - point[1])
    local_mask = local_dist <= 6.0
    local_collect_value = float(np.max(b[local_mask])) if np.any(local_mask) else 0.0
    travel = float(np.linalg.norm(point - current))
    distance_penalty = planner.active_lambda * travel
    local_value = planner.active_local_collect_weight * local_collect_value
    if planner.mode == "active_entropy":
        return entropy_value - distance_penalty
    if planner.mode == "active_probability":
        return planner.active_mu * probability_value - distance_penalty
    if planner.mode == "active_no_distance":
        return (
            entropy_value
            + planner.active_alpha * candidate_value
            + planner.active_mu * probability_value
            + local_value
        )
    return (
        entropy_value
        + planner.active_alpha * candidate_value
        + planner.active_mu * probability_value
        + local_value
        - distance_penalty
    )


def next_active(current: np.ndarray, heading: float, prob_map: ProbabilityMap, world: WorldConfig, planner: PlannerConfig, fusion) -> np.ndarray:
    candidates = candidate_waypoints(world, planner)
    # Use radar FOV as the larger search envelope; camera will refine once nearby.
    scores = np.array([
        _score_candidate(c, current, heading, prob_map, planner, fusion.radar)
        for c in candidates
    ])
    return candidates[int(np.argmax(scores))]


def choose_next_goal(
    t: float,
    current: np.ndarray,
    heading: float,
    state: PlannerState,
    prob_map: ProbabilityMap,
    world: WorldConfig,
    robot: RobotConfig,
    planner: PlannerConfig,
    fusion,
    target_queue: TargetQueue,
) -> tuple[np.ndarray, str]:
    if state.current_route:
        return state.current_route[0], "route"
    if planner.mode in {"lawnmower", "lawnmower_sparse", "lawnmower_dense"}:
        return next_lawnmower(state), "coverage"
    if planner.mode == "greedy":
        return next_greedy(prob_map, current, state, robot.collect_radius_m), "greedy"
    if planner.mode == "detected_tsp":
        confirmed_targets = target_queue.confirmed_targets()
        if confirmed_targets:
            state.current_route = nearest_neighbor_route(current, confirmed_targets, planner.detected_batch_size)
            if state.current_route:
                return state.current_route[0], "route"
        return next_lawnmower(state), "coverage"
    if planner.mode == "hybrid":
        confirmed_targets = target_queue.confirmed_targets()
        mean_entropy = float(np.mean(entropy(prob_map.belief)))
        decision = choose_hybrid_mode(mean_entropy, len(confirmed_targets), planner)
        if decision == HybridDecision.ROUTE and confirmed_targets:
            state.current_route = nearest_neighbor_route(current, confirmed_targets, planner.hybrid_target_batch_size)
            if state.current_route:
                return state.current_route[0], decision.value
        return next_active(current, heading, prob_map, world, planner, fusion), decision.value
    active_modes = {"active", "active_entropy", "active_probability", "active_no_distance"}
    if planner.mode in active_modes:
        active_goal_reached = (
            state.active_goal is not None
            and np.linalg.norm(state.active_goal - current) <= robot.arrival_tolerance_m
        )
        if state.active_goal is None or active_goal_reached or t - state.last_replan_t >= planner.replan_interval_s:
            state.last_replan_t = t
            state.active_goal = next_active(current, heading, prob_map, world, planner, fusion)
        return state.active_goal, "active"
    return next_greedy(prob_map, current, state, robot.collect_radius_m), "greedy"


def pop_arrived_route_goal(
    state: PlannerState,
    current: np.ndarray,
    tolerance: float,
    target_queue: TargetQueue | None = None,
    remove_radius_m: float | None = None,
) -> None:
    if state.current_route and np.linalg.norm(state.current_route[0] - current) <= tolerance:
        if target_queue is not None and remove_radius_m is not None:
            target_queue.remove_near(state.current_route[0], remove_radius_m)
        state.current_route.pop(0)
