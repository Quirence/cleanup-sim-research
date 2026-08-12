from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .config import PlannerConfig, PlatformConfig, WorldConfig
from .mapping import DensityMap, entropy
from .targets import TargetQueue
from .world import DebrisField


BELIEF_HORIZON_MODES = {
    "belief_horizon",
    "belief_horizon_provisional",
    "belief_horizon_no_efficiency",
    "belief_horizon_no_track_prediction",
    "belief_horizon_no_refinement",
}

BELIEF_ORIENTEERING_MODES = {
    "belief_orienteering",
    "belief_orienteering_provisional",
    "belief_orienteering_depth1",
    "belief_orienteering_no_opportunity_cost",
    "belief_orienteering_density_disabled",
}


@dataclass
class PlannerState:
    coverage_route: list[np.ndarray]
    coverage_index: int = 0
    active_goal: np.ndarray | None = None
    last_replan_t_s: float = -1e9
    greedy_suppressed: np.ndarray | None = None
    current_route: list[np.ndarray] | None = None
    current_route_mode: str = "route"
    current_route_reason: str = "confirmed_target_route"
    current_route_details: dict[str, float | str] = field(default_factory=dict)
    oracle_route: list[np.ndarray] | None = None


@dataclass(frozen=True)
class GoalDecision:
    point: np.ndarray
    mode: str
    reason: str
    expected_value: float
    details: dict[str, float | str] = field(default_factory=dict)


@dataclass(frozen=True)
class _RouteCandidate:
    focus: np.ndarray
    kind: str
    confidence: float = 0.0
    age_s: float = 0.0
    uncertainty_m: float = 0.0


@dataclass
class _OrienteeringBeam:
    route: list[np.ndarray]
    foci: list[np.ndarray]
    kinds: list[str]
    cursor: np.ndarray
    work_map: DensityMap
    length_m: float = 0.0
    benefit: float = 0.0
    risk: float = 0.0
    expected_collection: float = 0.0
    information_gain: float = 0.0
    target_confirmation: float = 0.0
    first_leg_score: float = 0.0


def make_coverage_route(world: WorldConfig, planner: PlannerConfig) -> list[np.ndarray]:
    ys = np.arange(planner.coverage_margin_m, world.height_m - planner.coverage_margin_m + 1e-9, planner.coverage_spacing_m)
    x_min = planner.coverage_margin_m
    x_max = world.width_m - planner.coverage_margin_m
    if ys.size == 0:
        return [np.array(world.depot, dtype=float)]

    depot = np.array(world.depot, dtype=float)
    row_order = list(np.argsort(np.abs(ys - depot[1])))
    route: list[np.ndarray] = []
    cursor = depot
    for row_idx in row_order:
        y = float(ys[row_idx])
        endpoints = [np.array([x_min, y], dtype=float), np.array([x_max, y], dtype=float)]
        first_idx = int(np.argmin([np.linalg.norm(point - cursor) for point in endpoints]))
        first = endpoints[first_idx]
        second = endpoints[1 - first_idx]
        route.extend([first, second])
        cursor = second
    return route


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


def next_active(
    current: np.ndarray,
    state: PlannerState,
    density_map: DensityMap,
    world: WorldConfig,
    platform: PlatformConfig,
    planner: PlannerConfig,
) -> np.ndarray:
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
        return next_greedy(state, density_map, current, platform)
    return candidates[int(np.argmax(scores))].astype(float)


def _top_grid_points(
    score: np.ndarray,
    density_map: DensityMap,
    count: int,
    min_distance_m: float,
    suppressed: np.ndarray | None = None,
) -> list[np.ndarray]:
    score = score.copy()
    if suppressed is not None and suppressed.shape == score.shape:
        score[suppressed] = -np.inf
    flat_order = np.argsort(score.ravel())[::-1]
    points: list[np.ndarray] = []
    for flat_idx in flat_order:
        value = float(score.ravel()[flat_idx])
        if not np.isfinite(value) or value <= 0.0:
            break
        iy, ix = np.unravel_index(int(flat_idx), score.shape)
        point = np.array([density_map.grid.x_centers[ix], density_map.grid.y_centers[iy]], dtype=float)
        if all(np.linalg.norm(point - old) >= min_distance_m for old in points):
            points.append(point)
        if len(points) >= count:
            break
    return points


def _relative_signal(values: np.ndarray) -> float:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return 0.0
    baseline = float(np.median(finite))
    peak = float(np.max(finite))
    return float((peak - baseline) / max(abs(baseline), 1e-9))


def _swept_expected_count(
    density_map: DensityMap,
    start: np.ndarray,
    goal: np.ndarray,
    platform: PlatformConfig,
) -> float:
    mask = _swept_mask(density_map, start, goal, platform)
    if not np.any(mask):
        return 0.0
    return float(np.sum(density_map.expected_count[mask]) * platform.capture_probability)


def _swept_mask(
    density_map: DensityMap,
    start: np.ndarray,
    goal: np.ndarray,
    platform: PlatformConfig,
) -> np.ndarray:
    direction = goal - start
    dist = float(np.linalg.norm(direction))
    if dist <= 1e-9:
        return np.zeros_like(density_map.expected_count, dtype=bool)
    direction = direction / dist
    rel_x = density_map.grid.xx - start[0]
    rel_y = density_map.grid.yy - start[1]
    along = rel_x * direction[0] + rel_y * direction[1]
    lateral = np.abs(rel_x * direction[1] - rel_y * direction[0])
    return (
        (along >= -0.15 * platform.collection_length_m)
        & (along <= dist + platform.collection_length_m)
        & (lateral <= 0.5 * platform.collection_width_m)
    )


def _point_in_swept_segment(
    start: np.ndarray,
    goal: np.ndarray,
    point: np.ndarray,
    platform: PlatformConfig,
    margin_m: float = 0.0,
) -> bool:
    direction = goal - start
    dist = float(np.linalg.norm(direction))
    if dist <= 1e-9:
        return bool(np.linalg.norm(point - start) <= platform.arrival_tolerance_m + margin_m)
    direction = direction / dist
    rel = point - start
    along = float(rel[0] * direction[0] + rel[1] * direction[1])
    lateral = abs(float(rel[0] * direction[1] - rel[1] * direction[0]))
    return (
        along >= -0.15 * platform.collection_length_m - margin_m
        and along <= dist + platform.collection_length_m + margin_m
        and lateral <= 0.5 * platform.collection_width_m + margin_m
    )


def _transect_endpoint(
    current: np.ndarray,
    focus: np.ndarray,
    world: WorldConfig,
    platform: PlatformConfig,
    planner: PlannerConfig,
) -> np.ndarray | None:
    direction = focus - current
    dist = float(np.linalg.norm(direction))
    if dist <= max(platform.arrival_tolerance_m, 0.25 * platform.collection_length_m):
        return None
    direction = direction / dist
    extension_m = max(
        planner.belief_transect_extension_m,
        2.0 * platform.collection_length_m,
        0.5 * platform.collection_width_m,
    )
    endpoint = focus + direction * extension_m
    endpoint = np.clip(endpoint, [0.0, 0.0], [world.width_m, world.height_m])
    if np.linalg.norm(endpoint - current) <= max(platform.arrival_tolerance_m, 0.25 * planner.candidate_spacing_m):
        return None
    return endpoint.astype(float)


def _discount_swept_density(
    density_map: DensityMap,
    start: np.ndarray,
    goal: np.ndarray,
    platform: PlatformConfig,
    planner: PlannerConfig,
) -> DensityMap:
    discounted = density_map.expected_count.copy()
    mask = _swept_mask(density_map, start, goal, platform)
    if np.any(mask):
        discount = float(np.clip(planner.belief_virtual_collection_discount * platform.capture_probability, 0.0, 1.0))
        discounted[mask] *= 1.0 - discount
    return DensityMap(grid=density_map.grid, expected_count=discounted)


def _best_followup_collection(
    density_map: DensityMap,
    current: np.ndarray,
    world: WorldConfig,
    platform: PlatformConfig,
    planner: PlannerConfig,
    suppressed: np.ndarray | None,
) -> float:
    min_sep = max(planner.candidate_spacing_m, platform.collection_width_m * 3.0)
    followup_points = _top_grid_points(
        density_map.expected_count,
        density_map,
        max(1, min(planner.belief_density_peak_count, planner.belief_transect_count)),
        min_sep,
        suppressed,
    )
    if not followup_points:
        return 0.0

    best = 0.0
    for focus in followup_points:
        direct = _swept_expected_count(density_map, current, focus, platform)
        best = max(best, direct)
        endpoint = _transect_endpoint(current, focus, world, platform, planner)
        if endpoint is not None:
            transect = _swept_expected_count(density_map, current, endpoint, platform)
            best = max(best, transect)
    return float(best)


def _local_entropy_gain(density_map: DensityMap, point: np.ndarray, radius_m: float) -> float:
    h = entropy(density_map.occupancy)
    dist = np.hypot(density_map.grid.xx - point[0], density_map.grid.yy - point[1])
    mask = dist <= radius_m
    if not np.any(mask):
        return 0.0
    return float(np.mean(h[mask]))


def _local_expected_count(density_map: DensityMap, point: np.ndarray, radius_m: float) -> float:
    dist = np.hypot(density_map.grid.xx - point[0], density_map.grid.yy - point[1])
    mask = dist <= radius_m
    if not np.any(mask):
        return 0.0
    return float(np.sum(density_map.expected_count[mask]))


def _target_tracks(targets: TargetQueue, t_s: float) -> list:
    targets.prune(t_s)
    return [track for track in targets.tracks if track.confirmed(targets.planner)]


def _provisional_target_tracks(targets: TargetQueue, t_s: float, planner: PlannerConfig) -> list:
    if not planner.belief_provisional_targets_enabled:
        return []
    targets.prune(t_s)
    tracks = []
    for track in targets.tracks:
        if track.confirmed(planner):
            continue
        if track.confidence < planner.belief_provisional_min_confidence:
            continue
        if track.hits < planner.belief_provisional_min_hits:
            continue
        if planner.belief_provisional_require_camera and "camera" not in track.sensors:
            continue
        if float(getattr(track, "localization_sigma_m", 0.0)) > planner.belief_provisional_max_uncertainty_m:
            continue
        tracks.append(track)
    return tracks


def _is_target_candidate(kind: str) -> bool:
    return kind.startswith("confirmed_target") or kind.startswith("provisional_target")


def _target_needs_refinement(track, platform: PlatformConfig, planner: PlannerConfig) -> bool:
    if not planner.belief_refinement_enabled:
        return False
    sigma_limit = max(planner.belief_collect_sigma_threshold_m, 0.5 * platform.collection_width_m)
    if planner.belief_require_camera_before_collection and "camera" not in track.sensors:
        return True
    return float(getattr(track, "localization_sigma_m", 0.0)) > sigma_limit


def _target_refine_waypoint(
    current: np.ndarray,
    target: np.ndarray,
    world: WorldConfig,
    platform: PlatformConfig,
    planner: PlannerConfig,
) -> np.ndarray | None:
    direction = target - current
    dist = float(np.linalg.norm(direction))
    if dist <= platform.arrival_tolerance_m:
        return None
    direction = direction / dist
    standoff = max(planner.belief_refine_standoff_m, platform.collection_approach_radius_m)
    point = target.copy() if dist <= standoff else target - direction * standoff
    point = np.clip(point, [0.0, 0.0], [world.width_m, world.height_m])
    if np.linalg.norm(point - current) <= platform.arrival_tolerance_m:
        return None
    return point.astype(float)


def _local_sweep_route(
    current: np.ndarray,
    target: np.ndarray,
    world: WorldConfig,
    platform: PlatformConfig,
    planner: PlannerConfig,
) -> list[np.ndarray]:
    direction = target - current
    dist = float(np.linalg.norm(direction))
    if dist <= 1e-9:
        direction = np.array([1.0, 0.0], dtype=float)
    else:
        direction = direction / dist
    perp = np.array([-direction[1], direction[0]], dtype=float)
    extension = max(planner.belief_transect_extension_m, 2.0 * platform.collection_length_m)
    spacing = max(planner.belief_local_sweep_spacing_m, 0.75 * platform.collection_width_m)
    lanes = max(1, int(planner.belief_local_sweep_lanes))
    offsets = [0.0]
    for lane in range(1, lanes):
        side = 1.0 if lane % 2 == 1 else -1.0
        rank = (lane + 1) // 2
        offsets.append(side * rank * spacing)

    route: list[np.ndarray] = []
    for lane, offset in enumerate(offsets):
        focus = target + perp * offset
        before = focus - direction * extension
        after = focus + direction * extension
        point = after if lane % 2 == 0 else before
        route.append(np.clip(point, [0.0, 0.0], [world.width_m, world.height_m]).astype(float))
    return route


def _best_ready_target_track(
    current: np.ndarray,
    tracks: list,
    t_s: float,
    platform: PlatformConfig,
    planner: PlannerConfig,
):
    best_track = None
    best_score = -np.inf
    for track in tracks:
        if _target_needs_refinement(track, platform, planner):
            continue
        travel = float(np.linalg.norm(track.position - current))
        age_s = max(0.0, t_s - track.last_seen_s)
        stale_risk = min(1.0, age_s / max(1.0, planner.target_stale_after_s))
        score = float(track.confidence) - planner.belief_path_cost_weight * travel - planner.belief_stale_target_risk_weight * stale_risk
        if score > best_score:
            best_score = score
            best_track = track
    return best_track, float(best_score)


def _belief_candidates(
    current: np.ndarray,
    state: PlannerState,
    density_map: DensityMap,
    world: WorldConfig,
    platform: PlatformConfig,
    planner: PlannerConfig,
    targets: TargetQueue,
    t_s: float,
) -> list[tuple[np.ndarray, str, float, float, float]]:
    candidates: list[tuple[np.ndarray, str, float, float, float]] = []
    target_candidates: list[tuple[np.ndarray, str, float, float, float]] = []
    for track in _target_tracks(targets, t_s):
        age_s = max(0.0, t_s - track.last_seen_s)
        uncertainty_m = float(getattr(track, "localization_sigma_m", 0.0))
        if _target_needs_refinement(track, platform, planner):
            refine = _target_refine_waypoint(current, track.position, world, platform, planner)
            if refine is not None:
                target_candidates.append((refine, "confirmed_target_refine", float(track.confidence), age_s, uncertainty_m))
            continue
        target_candidates.append((track.position.copy(), "confirmed_target", float(track.confidence), age_s, uncertainty_m))
        endpoint = _transect_endpoint(current, track.position, world, platform, planner)
        if endpoint is not None:
            target_candidates.append((endpoint, "confirmed_target_transect", float(track.confidence), age_s, uncertainty_m))

    confirmed_target_candidate_count = len(target_candidates)

    for track in _provisional_target_tracks(targets, t_s, planner):
        age_s = max(0.0, t_s - track.last_seen_s)
        uncertainty_m = float(getattr(track, "localization_sigma_m", 0.0))
        confidence = float(track.confidence) * planner.belief_provisional_confidence_scale
        if _target_needs_refinement(track, platform, planner):
            refine = _target_refine_waypoint(current, track.position, world, platform, planner)
            if refine is not None:
                target_candidates.append((refine, "provisional_target_refine", confidence, age_s, uncertainty_m))
            continue
        target_candidates.append((track.position.copy(), "provisional_target", confidence, age_s, uncertainty_m))
        endpoint = _transect_endpoint(current, track.position, world, platform, planner)
        if endpoint is not None:
            target_candidates.append((endpoint, "provisional_target_transect", confidence, age_s, uncertainty_m))

    candidates.extend(target_candidates)

    min_sep = max(planner.candidate_spacing_m, platform.collection_width_m * 3.0)
    density_points: list[np.ndarray] = []
    if confirmed_target_candidate_count == 0 and _relative_signal(density_map.expected_count) >= planner.belief_density_signal_threshold:
        density_points = _top_grid_points(
            density_map.expected_count,
            density_map,
            planner.belief_density_peak_count,
            min_sep,
            state.greedy_suppressed,
        )
        candidates.extend((point, "density_peak", 0.0, 0.0, 0.0) for point in density_points)
        for point in density_points[: planner.belief_transect_count]:
            endpoint = _transect_endpoint(current, point, world, platform, planner)
            if endpoint is not None:
                candidates.append((endpoint, "density_transect", 0.0, 0.0, 0.0))

    h = entropy(density_map.occupancy)
    if confirmed_target_candidate_count == 0 and _relative_signal(h) >= planner.belief_entropy_signal_threshold:
        entropy_points = _top_grid_points(h, density_map, planner.belief_entropy_peak_count, min_sep, state.greedy_suppressed)
        candidates.extend((point, "entropy_peak", 0.0, 0.0, 0.0) for point in entropy_points)

    if confirmed_target_candidate_count == 0 and not density_points and state.coverage_route:
        min_route_travel = max(platform.arrival_tolerance_m, 0.5 * planner.candidate_spacing_m)
        while (
            state.coverage_index < len(state.coverage_route) - 1
            and np.linalg.norm(state.coverage_route[state.coverage_index] - current) <= min_route_travel
        ):
            state.coverage_index += 1
        idx = min(state.coverage_index, len(state.coverage_route) - 1)
        candidates.append((state.coverage_route[idx].copy(), "coverage_route", 0.0, 0.0, 0.0))

    base_waypoints = candidate_waypoints(world, planner)
    if confirmed_target_candidate_count == 0 and not density_points and base_waypoints.size:
        distances = np.linalg.norm(base_waypoints - current, axis=1)
        far_enough = distances > max(platform.arrival_tolerance_m, 0.25 * planner.candidate_spacing_m)
        ordered = np.argsort(distances + 0.15 * np.arange(len(distances)))
        for idx in ordered:
            if far_enough[idx]:
                candidates.append((base_waypoints[idx].astype(float), "coverage_fallback", 0.0, 0.0, 0.0))
                break

    # Deduplicate near-identical candidates while preserving source priority.
    unique: list[tuple[np.ndarray, str, float, float, float]] = []
    for point, kind, confidence, age_s, uncertainty_m in candidates:
        clipped = np.clip(point.astype(float), [0.0, 0.0], [world.width_m, world.height_m])
        travel = float(np.linalg.norm(clipped - current))
        if (
            kind in {"density_peak", "density_transect", "entropy_peak", "coverage_fallback"}
            and travel > planner.belief_unconfirmed_candidate_max_travel_m
        ):
            continue
        min_travel = platform.arrival_tolerance_m
        if kind not in {"confirmed_target", "confirmed_target_refine", "provisional_target", "provisional_target_refine", "depot"}:
            min_travel = max(min_travel, 0.5 * planner.candidate_spacing_m)
        if travel <= min_travel:
            continue
        if any(np.linalg.norm(clipped - old[0]) <= platform.arrival_tolerance_m for old in unique):
            continue
        unique.append((clipped, kind, confidence, age_s, uncertainty_m))
        if len(unique) >= planner.belief_candidate_count:
            break
    return unique


def next_belief_horizon(
    t_s: float,
    current: np.ndarray,
    state: PlannerState,
    density_map: DensityMap,
    world: WorldConfig,
    platform: PlatformConfig,
    planner: PlannerConfig,
    targets: TargetQueue,
) -> GoalDecision:
    tracks = _target_tracks(targets, t_s)
    ready_track, ready_score = _best_ready_target_track(current, tracks, t_s, platform, planner)
    if planner.belief_local_sweep_enabled and ready_track is not None:
        route = _local_sweep_route(current, ready_track.position, world, platform, planner)
        route = [point for point in route if np.linalg.norm(point - current) > platform.arrival_tolerance_m]
        if route:
            state.current_route = route
            state.current_route_mode = "belief_horizon"
            state.current_route_reason = "confirmed_target_local_sweep"
            state.current_route_details = {
                "candidate_type": "confirmed_target_local_sweep",
                "score_total": ready_score,
                "score_expected_collection": 0.0,
                "score_rollout_collection": 0.0,
                "score_information_gain": 0.0,
                "score_target_confirmation": float(ready_track.confidence),
                "score_refine_bonus": 0.0,
                "score_empty_risk": 0.0,
                "score_stale_risk": min(1.0, max(0.0, t_s - ready_track.last_seen_s) / max(1.0, planner.target_stale_after_s)),
                "score_path_cost": float(np.linalg.norm(route[0] - current)),
                "target_uncertainty_m": float(getattr(ready_track, "localization_sigma_m", 0.0)),
                "local_sweep_lanes": float(len(route)),
            }
            return GoalDecision(
                route[0].copy(),
                state.current_route_mode,
                state.current_route_reason,
                ready_score,
                dict(state.current_route_details),
            )

    candidates = _belief_candidates(current, state, density_map, world, platform, planner, targets, t_s)
    if not candidates:
        point = next_active(current, state, density_map, world, platform, planner)
        return GoalDecision(point, "belief_horizon", "belief_fallback_active", 0.0, {"candidate_type": "fallback"})

    best: GoalDecision | None = None
    for point, kind, confidence, age_s, uncertainty_m in candidates:
        travel = float(np.linalg.norm(point - current))
        expected_collection = _swept_expected_count(density_map, current, point, platform)
        post_pass_map = _discount_swept_density(density_map, current, point, platform, planner)
        rollout_collection = _best_followup_collection(
            post_pass_map,
            point,
            world,
            platform,
            planner,
            state.greedy_suppressed,
        )
        information_gain = _local_entropy_gain(density_map, point, planner.candidate_spacing_m)
        target_confirmation = confidence if _is_target_candidate(kind) and not kind.endswith("_refine") else 0.0
        refine_bonus = confidence if kind.endswith("_refine") else 0.0
        empty_risk = float(np.exp(-max(0.0, expected_collection)))
        stale_risk = min(1.0, age_s / max(1.0, planner.target_stale_after_s))
        path_cost = travel
        depot_bonus = 0.0
        if kind == "depot":
            depot_bonus = -0.25

        benefit = (
            planner.belief_expected_collection_weight * expected_collection
            + planner.belief_rollout_collection_weight * rollout_collection
            + planner.belief_information_gain_weight * information_gain
            + planner.belief_target_confirmation_weight * target_confirmation
            + planner.belief_refine_confidence_weight * refine_bonus
        )
        risk_penalty = (
            planner.belief_empty_goal_risk_weight * empty_risk
            + planner.belief_stale_target_risk_weight * stale_risk
        )
        effort_m = max(path_cost, platform.collection_approach_radius_m)
        if planner.belief_efficiency_score:
            score = planner.belief_efficiency_scale_m * benefit / effort_m - risk_penalty
        else:
            score = (
                benefit
                - planner.belief_path_cost_weight * path_cost
                - risk_penalty
            )
        score += depot_bonus
        details: dict[str, float | str] = {
            "candidate_type": kind,
            "score_total": float(score),
            "score_benefit": float(benefit),
            "score_risk_penalty": float(risk_penalty),
            "score_effort_m": float(effort_m),
            "score_expected_collection": float(expected_collection),
            "score_rollout_collection": float(rollout_collection),
            "score_information_gain": float(information_gain),
            "score_target_confirmation": float(target_confirmation),
            "score_refine_bonus": float(refine_bonus),
            "score_empty_risk": float(empty_risk),
            "score_stale_risk": float(stale_risk),
            "score_path_cost": float(path_cost),
            "target_uncertainty_m": float(uncertainty_m),
        }
        decision = GoalDecision(point, "belief_horizon", "belief_horizon_score", float(score), details)
        if best is None or decision.expected_value > best.expected_value:
            best = decision

    assert best is not None
    return best


def _cluster_route_focus_candidates(
    t_s: float,
    current: np.ndarray,
    state: PlannerState,
    density_map: DensityMap,
    world: WorldConfig,
    platform: PlatformConfig,
    planner: PlannerConfig,
    targets: TargetQueue,
) -> list[_RouteCandidate]:
    candidates: list[_RouteCandidate] = []
    for track in _target_tracks(targets, t_s):
        if _target_needs_refinement(track, platform, planner):
            continue
        candidates.append(
            _RouteCandidate(
                focus=np.clip(track.position.copy(), [0.0, 0.0], [world.width_m, world.height_m]),
                kind="confirmed_target",
                confidence=float(track.confidence),
                age_s=max(0.0, t_s - track.last_seen_s),
                uncertainty_m=float(getattr(track, "localization_sigma_m", 0.0)),
            )
        )

    min_sep = max(0.5 * planner.candidate_spacing_m, platform.collection_width_m * 2.0)
    if _relative_signal(density_map.expected_count) >= planner.belief_density_signal_threshold:
        density_points = _top_grid_points(
            density_map.expected_count,
            density_map,
            planner.belief_cluster_route_candidate_count,
            min_sep,
            state.greedy_suppressed,
        )
        candidates.extend(_RouteCandidate(point, "density_peak") for point in density_points)

    if not candidates and _relative_signal(entropy(density_map.occupancy)) >= planner.belief_entropy_signal_threshold:
        entropy_points = _top_grid_points(
            entropy(density_map.occupancy),
            density_map,
            planner.belief_entropy_peak_count,
            min_sep,
            state.greedy_suppressed,
        )
        candidates.extend(_RouteCandidate(point, "entropy_peak") for point in entropy_points)

    unique: list[_RouteCandidate] = []
    for candidate in candidates:
        focus = np.clip(candidate.focus.astype(float), [0.0, 0.0], [world.width_m, world.height_m])
        travel = float(np.linalg.norm(focus - current))
        if travel <= max(platform.arrival_tolerance_m, 0.25 * planner.candidate_spacing_m):
            continue
        if candidate.kind in {"density_peak", "entropy_peak"} and travel > planner.belief_unconfirmed_candidate_max_travel_m:
            continue
        if any(np.linalg.norm(focus - old.focus) <= min_sep for old in unique):
            continue
        unique.append(
            _RouteCandidate(
                focus=focus,
                kind=candidate.kind,
                confidence=candidate.confidence,
                age_s=candidate.age_s,
                uncertainty_m=candidate.uncertainty_m,
            )
        )

    scored = [
        (_cluster_route_individual_score(current, candidate, density_map, world, platform, planner), candidate)
        for candidate in unique
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    return [candidate for score, candidate in scored[: max(1, planner.belief_cluster_route_candidate_count)] if score > -np.inf]


def _cluster_route_individual_score(
    current: np.ndarray,
    candidate: _RouteCandidate,
    density_map: DensityMap,
    world: WorldConfig,
    platform: PlatformConfig,
    planner: PlannerConfig,
) -> float:
    endpoint = _cluster_route_endpoint(current, candidate, world, platform, planner)
    travel = float(np.linalg.norm(endpoint - current))
    if travel <= platform.arrival_tolerance_m:
        return -np.inf
    swept = _swept_expected_count(density_map, current, endpoint, platform)
    local_density = _local_expected_count(
        density_map,
        candidate.focus,
        max(planner.candidate_spacing_m, 2.5 * platform.collection_width_m),
    )
    information = _local_entropy_gain(density_map, candidate.focus, planner.candidate_spacing_m)
    target_confirmation = candidate.confidence if candidate.kind.startswith("confirmed_target") else 0.0
    benefit = (
        planner.belief_expected_collection_weight * max(swept, planner.belief_cluster_route_density_prior_weight * local_density)
        + planner.belief_information_gain_weight * information
        + planner.belief_target_confirmation_weight * target_confirmation
    )
    stale_risk = min(1.0, candidate.age_s / max(1.0, planner.target_stale_after_s))
    risk = planner.belief_stale_target_risk_weight * stale_risk
    return planner.belief_efficiency_scale_m * benefit / max(travel, platform.collection_approach_radius_m) - risk


def _cluster_route_endpoint(
    start: np.ndarray,
    candidate: _RouteCandidate,
    world: WorldConfig,
    platform: PlatformConfig,
    planner: PlannerConfig,
) -> np.ndarray:
    if candidate.kind in {"confirmed_target", "provisional_target", "density_peak"}:
        endpoint = _transect_endpoint(start, candidate.focus, world, platform, planner)
        if endpoint is not None:
            return endpoint
    return np.clip(candidate.focus.copy(), [0.0, 0.0], [world.width_m, world.height_m]).astype(float)


def _sequence_route_candidates(
    current: np.ndarray,
    candidates: list[_RouteCandidate],
    planner: PlannerConfig,
) -> list[_RouteCandidate]:
    remaining = list(candidates)
    sequence: list[_RouteCandidate] = []
    cursor = current.copy()
    while remaining and len(sequence) < max(1, planner.belief_cluster_route_max_points):
        distances = [float(np.linalg.norm(candidate.focus - cursor)) for candidate in remaining]
        idx = int(np.argmin(distances))
        chosen = remaining.pop(idx)
        sequence.append(chosen)
        cursor = chosen.focus.copy()
    return sequence


def _cluster_route_points(
    current: np.ndarray,
    sequence: list[_RouteCandidate],
    world: WorldConfig,
    platform: PlatformConfig,
    planner: PlannerConfig,
) -> list[np.ndarray]:
    route: list[np.ndarray] = []
    cursor = current.copy()
    for candidate in sequence:
        endpoint = _cluster_route_endpoint(cursor, candidate, world, platform, planner)
        if np.linalg.norm(endpoint - cursor) <= platform.arrival_tolerance_m:
            continue
        if route and np.linalg.norm(endpoint - route[-1]) <= platform.arrival_tolerance_m:
            continue
        route.append(endpoint.astype(float))
        cursor = endpoint.astype(float)
    return route


def _score_cluster_route(
    current: np.ndarray,
    sequence: list[_RouteCandidate],
    route: list[np.ndarray],
    density_map: DensityMap,
    platform: PlatformConfig,
    planner: PlannerConfig,
) -> tuple[float, dict[str, float | str]]:
    route_length = _route_length(current, route)
    if route_length <= platform.arrival_tolerance_m or route_length > planner.belief_cluster_route_max_length_m:
        return -np.inf, {}

    work_map = DensityMap(grid=density_map.grid, expected_count=density_map.expected_count.copy())
    cursor = current.copy()
    expected_total = 0.0
    information_total = 0.0
    target_confirmation_total = 0.0
    empty_risk_total = 0.0
    stale_risk_total = 0.0
    uncertainty_total = 0.0
    for candidate, point in zip(sequence, route):
        expected_collection = _swept_expected_count(work_map, cursor, point, platform)
        expected_total += expected_collection
        information_total += _local_entropy_gain(work_map, candidate.focus, planner.candidate_spacing_m)
        if candidate.kind.startswith("confirmed_target"):
            target_confirmation_total += candidate.confidence
        empty_risk_total += float(np.exp(-max(0.0, expected_collection)))
        stale_risk_total += min(1.0, candidate.age_s / max(1.0, planner.target_stale_after_s))
        uncertainty_total += candidate.uncertainty_m
        work_map = _discount_swept_density(work_map, cursor, point, platform, planner)
        cursor = point.copy()

    point_count = max(1, len(route))
    benefit = (
        planner.belief_expected_collection_weight * expected_total
        + planner.belief_information_gain_weight * information_total
        + planner.belief_target_confirmation_weight * target_confirmation_total
    )
    risk_penalty = (
        planner.belief_empty_goal_risk_weight * empty_risk_total / point_count
        + planner.belief_stale_target_risk_weight * stale_risk_total / point_count
    )
    score = planner.belief_efficiency_scale_m * benefit / max(route_length, platform.collection_approach_radius_m) - risk_penalty
    details: dict[str, float | str] = {
        "candidate_type": "cluster_route_transect",
        "score_total": float(score),
        "score_benefit": float(benefit),
        "score_risk_penalty": float(risk_penalty),
        "score_effort_m": float(route_length),
        "score_expected_collection": float(expected_total),
        "score_rollout_collection": 0.0,
        "score_information_gain": float(information_total),
        "score_target_confirmation": float(target_confirmation_total),
        "score_refine_bonus": 0.0,
        "score_empty_risk": float(empty_risk_total / point_count),
        "score_stale_risk": float(stale_risk_total / point_count),
        "score_path_cost": float(route_length),
        "target_uncertainty_m": float(uncertainty_total / point_count),
        "cluster_route_points": float(len(route)),
        "cluster_route_length_m": float(route_length),
    }
    return float(score), details


def _augment_fallback_with_cluster_route(
    fallback: GoalDecision,
    t_s: float,
    current: np.ndarray,
    candidates: list[_RouteCandidate],
    density_map: DensityMap,
    world: WorldConfig,
    platform: PlatformConfig,
    planner: PlannerConfig,
) -> tuple[list[np.ndarray] | None, dict[str, float | str], float]:
    fallback_kind = str(fallback.details.get("candidate_type", "fallback"))
    if fallback_kind in {"confirmed_target_refine", "fallback", "coverage_route", "coverage_fallback"}:
        return None, {}, -np.inf

    first_point = np.clip(fallback.point.copy(), [0.0, 0.0], [world.width_m, world.height_m])
    first_distance = float(np.linalg.norm(first_point - current))
    if first_distance <= platform.arrival_tolerance_m:
        return None, {}, -np.inf

    anchor = _RouteCandidate(
        focus=first_point.copy(),
        kind=fallback_kind,
        confidence=float(fallback.details.get("score_target_confirmation", 0.0)),
        age_s=float(fallback.details.get("score_stale_risk", 0.0)) * max(1.0, planner.target_stale_after_s),
        uncertainty_m=float(fallback.details.get("target_uncertainty_m", 0.0)),
    )
    route = [first_point]
    sequence = [anchor]
    cursor = first_point.copy()
    route_length = first_distance
    work_map = _discount_swept_density(density_map, current, first_point, platform, planner)
    remaining = [
        candidate
        for candidate in candidates
        if not _point_in_swept_segment(current, first_point, candidate.focus, platform, margin_m=platform.collection_width_m)
    ]

    while len(route) < max(1, planner.belief_cluster_route_max_points):
        best_candidate: _RouteCandidate | None = None
        best_endpoint: np.ndarray | None = None
        best_score = -np.inf
        for candidate in remaining:
            near_route = min(float(np.linalg.norm(candidate.focus - point)) for point in route)
            if near_route > planner.belief_cluster_route_radius_m:
                continue
            endpoint = _cluster_route_endpoint(cursor, candidate, world, platform, planner)
            added_distance = float(np.linalg.norm(endpoint - cursor))
            if added_distance <= platform.arrival_tolerance_m:
                continue
            if route_length + added_distance > planner.belief_cluster_route_max_length_m:
                continue
            expected_collection = _swept_expected_count(work_map, cursor, endpoint, platform)
            local_density = _local_expected_count(
                work_map,
                candidate.focus,
                max(planner.candidate_spacing_m, 2.5 * platform.collection_width_m),
            )
            information_gain = _local_entropy_gain(work_map, candidate.focus, planner.candidate_spacing_m)
            target_confirmation = candidate.confidence if candidate.kind.startswith("confirmed_target") else 0.0
            stale_risk = min(1.0, candidate.age_s / max(1.0, planner.target_stale_after_s))
            benefit = (
                planner.belief_expected_collection_weight * max(expected_collection, planner.belief_cluster_route_density_prior_weight * local_density)
                + planner.belief_information_gain_weight * information_gain
                + planner.belief_target_confirmation_weight * target_confirmation
            )
            risk_penalty = (
                planner.belief_empty_goal_risk_weight * float(np.exp(-max(0.0, expected_collection)))
                + planner.belief_stale_target_risk_weight * stale_risk
            )
            marginal_score = (
                planner.belief_efficiency_scale_m * benefit / max(added_distance, platform.collection_approach_radius_m)
                - risk_penalty
            )
            if marginal_score > best_score:
                best_score = marginal_score
                best_candidate = candidate
                best_endpoint = endpoint
        if best_candidate is None or best_endpoint is None or best_score <= planner.belief_cluster_route_switch_margin:
            break
        route.append(best_endpoint.astype(float))
        sequence.append(best_candidate)
        work_map = _discount_swept_density(work_map, cursor, best_endpoint, platform, planner)
        cursor = best_endpoint.astype(float)
        route_length += float(np.linalg.norm(route[-1] - (route[-2] if len(route) > 1 else current)))
        remaining = [
            candidate
            for candidate in remaining
            if candidate is not best_candidate
            and not _point_in_swept_segment(route[-2], route[-1], candidate.focus, platform, margin_m=platform.collection_width_m)
        ]

    if len(route) < max(1, planner.belief_cluster_route_min_points):
        return None, {}, -np.inf
    score, details = _score_cluster_route(current, sequence, route, density_map, platform, planner)
    return route, details, score


def next_belief_cluster_route(
    t_s: float,
    current: np.ndarray,
    state: PlannerState,
    density_map: DensityMap,
    world: WorldConfig,
    platform: PlatformConfig,
    planner: PlannerConfig,
    targets: TargetQueue,
) -> GoalDecision:
    fallback = next_belief_horizon(t_s, current, state, density_map, world, platform, planner, targets)
    if state.current_route:
        return fallback

    candidates = _cluster_route_focus_candidates(t_s, current, state, density_map, world, platform, planner, targets)
    route_candidates = (
        [candidate for candidate in candidates if candidate.kind == "confirmed_target"]
        if planner.belief_cluster_route_confirmed_followups_only
        else candidates
    )
    augmented_route, augmented_details, augmented_score = _augment_fallback_with_cluster_route(
        fallback,
        t_s,
        current,
        route_candidates,
        density_map,
        world,
        platform,
        planner,
    )
    if augmented_route is not None:
        state.current_route = augmented_route
        state.current_route_mode = "belief_horizon"
        state.current_route_reason = "belief_cluster_route"
        state.current_route_details = augmented_details
        return GoalDecision(
            augmented_route[0].copy(),
            state.current_route_mode,
            state.current_route_reason,
            float(augmented_score),
            dict(augmented_details),
        )

    if len(route_candidates) < max(1, planner.belief_cluster_route_min_points):
        return fallback

    candidate_scores = {
        id(candidate): _cluster_route_individual_score(current, candidate, density_map, world, platform, planner)
        for candidate in route_candidates
    }
    ranked = sorted(route_candidates, key=lambda candidate: candidate_scores[id(candidate)], reverse=True)
    best_route: list[np.ndarray] | None = None
    best_details: dict[str, float | str] = {}
    best_score = -np.inf

    for seed_candidate in ranked[: max(1, planner.belief_cluster_route_candidate_count)]:
        neighbors = [
            candidate
            for candidate in ranked
            if np.linalg.norm(candidate.focus - seed_candidate.focus) <= planner.belief_cluster_route_radius_m
        ]
        if len(neighbors) < max(1, planner.belief_cluster_route_min_points):
            continue
        neighbors.sort(
            key=lambda candidate: (
                float(np.linalg.norm(candidate.focus - seed_candidate.focus)),
                -candidate_scores[id(candidate)],
            )
        )
        sequence = _sequence_route_candidates(current, neighbors[: planner.belief_cluster_route_candidate_count], planner)
        route = _cluster_route_points(current, sequence, world, platform, planner)
        if len(route) < max(1, planner.belief_cluster_route_min_points):
            continue
        score, details = _score_cluster_route(current, sequence[: len(route)], route, density_map, platform, planner)
        if score > best_score:
            best_score = score
            best_route = route
            best_details = details

    if best_route is None:
        return fallback

    if best_score <= fallback.expected_value + planner.belief_cluster_route_switch_margin:
        return fallback

    state.current_route = best_route
    state.current_route_mode = "belief_horizon"
    state.current_route_reason = "belief_cluster_route"
    state.current_route_details = best_details
    return GoalDecision(
        best_route[0].copy(),
        state.current_route_mode,
        state.current_route_reason,
        float(best_score),
        dict(best_details),
    )


def _as_orienteering_fallback(fallback: GoalDecision) -> GoalDecision:
    details = dict(fallback.details)
    details["orienteering_fallback_reason"] = fallback.reason
    details["orienteering_route_points"] = 1.0
    details["orienteering_route_length_m"] = float(details.get("score_path_cost", 0.0))
    return GoalDecision(
        fallback.point.copy(),
        "belief_orienteering",
        "belief_orienteering_fallback",
        fallback.expected_value,
        details,
    )


def _orienteering_candidates(
    current: np.ndarray,
    state: PlannerState,
    density_map: DensityMap,
    world: WorldConfig,
    platform: PlatformConfig,
    planner: PlannerConfig,
    targets: TargetQueue,
    t_s: float,
) -> list[_RouteCandidate]:
    allowed = {
        "confirmed_target",
        "provisional_target",
    }
    if planner.belief_orienteering_density_enabled:
        allowed |= {
            "density_peak",
        }
        if planner.belief_orienteering_entropy_enabled:
            allowed.add("entropy_peak")
    raw_candidates = _belief_candidates(current, state, density_map, world, platform, planner, targets, t_s)
    candidates: list[_RouteCandidate] = []
    for point, kind, confidence, age_s, uncertainty_m in raw_candidates:
        if kind not in allowed:
            continue
        candidate = _RouteCandidate(point.astype(float), kind, confidence, age_s, uncertainty_m)
        first_leg = _orienteering_leg_components(density_map, current, candidate, world, platform, planner)
        if first_leg["distance_m"] > planner.belief_orienteering_max_first_leg_m:
            continue
        if kind == "density_peak" and first_leg["expected_collection"] < planner.belief_orienteering_min_density_swept_count:
            continue
        candidates.append(candidate)
    scored = [
        (_orienteering_single_candidate_score(current, candidate, density_map, world, platform, planner), candidate)
        for candidate in candidates
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    unique: list[_RouteCandidate] = []
    for score, candidate in scored:
        if not np.isfinite(score):
            continue
        if any(np.linalg.norm(candidate.focus - old.focus) <= platform.arrival_tolerance_m for old in unique):
            continue
        unique.append(candidate)
        if len(unique) >= max(1, planner.belief_orienteering_candidate_count):
            break
    return unique


def _orienteering_goal_point(
    start: np.ndarray,
    candidate: _RouteCandidate,
    world: WorldConfig,
    platform: PlatformConfig,
    planner: PlannerConfig,
) -> np.ndarray:
    if candidate.kind in {"confirmed_target", "density_peak"}:
        endpoint = _transect_endpoint(start, candidate.focus, world, platform, planner)
        if endpoint is not None:
            return endpoint
    return np.clip(candidate.focus.copy(), [0.0, 0.0], [world.width_m, world.height_m]).astype(float)


def _orienteering_candidate_type(candidate: _RouteCandidate, goal: np.ndarray) -> str:
    if candidate.kind == "confirmed_target" and np.linalg.norm(goal - candidate.focus) > 1e-9:
        return "confirmed_target_transect"
    if candidate.kind == "provisional_target" and np.linalg.norm(goal - candidate.focus) > 1e-9:
        return "provisional_target_transect"
    if candidate.kind == "density_peak" and np.linalg.norm(goal - candidate.focus) > 1e-9:
        return "density_transect"
    return candidate.kind


def _orienteering_single_candidate_score(
    current: np.ndarray,
    candidate: _RouteCandidate,
    density_map: DensityMap,
    world: WorldConfig,
    platform: PlatformConfig,
    planner: PlannerConfig,
) -> float:
    leg = _orienteering_leg_components(density_map, current, candidate, world, platform, planner)
    effort = max(leg["distance_m"], platform.collection_approach_radius_m)
    return planner.belief_efficiency_scale_m * leg["benefit"] / effort - leg["risk"]


def _orienteering_leg_components(
    density_map: DensityMap,
    start: np.ndarray,
    candidate: _RouteCandidate,
    world: WorldConfig,
    platform: PlatformConfig,
    planner: PlannerConfig,
) -> dict[str, float]:
    goal = _orienteering_goal_point(start, candidate, world, platform, planner)
    distance_m = float(np.linalg.norm(goal - start))
    expected_collection = _swept_expected_count(density_map, start, goal, platform)
    local_density = _local_expected_count(
        density_map,
        candidate.focus,
        max(planner.candidate_spacing_m, 2.5 * platform.collection_width_m),
    )
    information_gain = _local_entropy_gain(density_map, candidate.focus, planner.candidate_spacing_m)
    target_confirmation = candidate.confidence if _is_target_candidate(candidate.kind) else 0.0
    empty_risk = float(np.exp(-max(0.0, expected_collection)))
    stale_risk = min(1.0, candidate.age_s / max(1.0, planner.target_stale_after_s))
    if candidate.kind == "density_peak":
        collection_value = expected_collection + planner.belief_orienteering_density_prior_weight * local_density
    elif _is_target_candidate(candidate.kind):
        collection_value = max(expected_collection, planner.belief_orienteering_target_density_prior_weight * local_density)
    else:
        collection_value = expected_collection
    benefit = (
        planner.belief_expected_collection_weight * collection_value
        + planner.belief_information_gain_weight * information_gain
        + planner.belief_target_confirmation_weight * target_confirmation
    )
    risk = (
        planner.belief_empty_goal_risk_weight * empty_risk
        + planner.belief_stale_target_risk_weight * stale_risk
    )
    return {
        "distance_m": distance_m,
        "goal_x": float(goal[0]),
        "goal_y": float(goal[1]),
        "expected_collection": expected_collection,
        "information_gain": information_gain,
        "target_confirmation": target_confirmation,
        "empty_risk": empty_risk,
        "stale_risk": stale_risk,
        "benefit": benefit,
        "risk": risk,
    }


def _orienteering_beam_score(beam: _OrienteeringBeam, platform: PlatformConfig, planner: PlannerConfig) -> float:
    if not beam.route:
        return -np.inf
    effort = max(beam.length_m, platform.collection_approach_radius_m)
    return planner.belief_efficiency_scale_m * beam.benefit / effort - beam.risk


def _candidate_repeated_in_route(
    candidate: _RouteCandidate,
    foci: list[np.ndarray],
    platform: PlatformConfig,
) -> bool:
    return any(np.linalg.norm(candidate.focus - point) <= max(platform.arrival_tolerance_m, platform.collection_width_m) for point in foci)


def _expand_orienteering_beams(
    beams: list[_OrienteeringBeam],
    candidates: list[_RouteCandidate],
    world: WorldConfig,
    platform: PlatformConfig,
    planner: PlannerConfig,
    depth_index: int,
) -> list[_OrienteeringBeam]:
    expanded: list[_OrienteeringBeam] = []
    discount = planner.belief_orienteering_future_discount ** depth_index
    for beam in beams:
        for candidate in candidates:
            if _candidate_repeated_in_route(candidate, beam.foci, platform):
                continue
            start = beam.cursor
            leg = _orienteering_leg_components(beam.work_map, start, candidate, world, platform, planner)
            if leg["distance_m"] <= platform.arrival_tolerance_m:
                continue
            if not beam.route and leg["distance_m"] > planner.belief_orienteering_max_first_leg_m:
                continue
            new_length = beam.length_m + leg["distance_m"]
            if new_length > planner.belief_orienteering_max_route_m:
                continue
            goal = np.array([leg["goal_x"], leg["goal_y"]], dtype=float)
            new_map = _discount_swept_density(beam.work_map, start, goal, platform, planner)
            first_leg_score = beam.first_leg_score
            if not beam.route:
                first_leg_score = planner.belief_efficiency_scale_m * leg["benefit"] / max(
                    leg["distance_m"],
                    platform.collection_approach_radius_m,
                ) - leg["risk"]
            expanded.append(
                _OrienteeringBeam(
                    route=[*beam.route, goal.copy()],
                    foci=[*beam.foci, candidate.focus.copy()],
                    kinds=[*beam.kinds, _orienteering_candidate_type(candidate, goal)],
                    cursor=goal.copy(),
                    work_map=new_map,
                    length_m=new_length,
                    benefit=beam.benefit + discount * leg["benefit"],
                    risk=beam.risk + discount * leg["risk"],
                    expected_collection=beam.expected_collection + discount * leg["expected_collection"],
                    information_gain=beam.information_gain + discount * leg["information_gain"],
                    target_confirmation=beam.target_confirmation + discount * leg["target_confirmation"],
                    first_leg_score=first_leg_score,
                )
            )
    expanded.sort(key=lambda beam: _orienteering_beam_score(beam, platform, planner), reverse=True)
    return expanded[: max(1, planner.belief_orienteering_beam_width)]


def next_belief_orienteering(
    t_s: float,
    current: np.ndarray,
    state: PlannerState,
    density_map: DensityMap,
    world: WorldConfig,
    platform: PlatformConfig,
    planner: PlannerConfig,
    targets: TargetQueue,
) -> GoalDecision:
    fallback = next_belief_horizon(t_s, current, state, density_map, world, platform, planner, targets)
    if state.current_route:
        return _as_orienteering_fallback(fallback)
    fallback_kind = str(fallback.details.get("candidate_type", "fallback"))
    if fallback_kind == "confirmed_target_refine":
        return _as_orienteering_fallback(fallback)

    candidates = _orienteering_candidates(current, state, density_map, world, platform, planner, targets, t_s)
    if not candidates:
        return _as_orienteering_fallback(fallback)

    initial_map = DensityMap(grid=density_map.grid, expected_count=density_map.expected_count.copy())
    beams = [
        _OrienteeringBeam(
            route=[],
            foci=[],
            kinds=[],
            cursor=current.copy(),
            work_map=initial_map,
        )
    ]
    completed: list[_OrienteeringBeam] = []
    for depth_index in range(max(1, planner.belief_orienteering_depth)):
        beams = _expand_orienteering_beams(beams, candidates, world, platform, planner, depth_index)
        completed.extend(beams)
        if not beams:
            break

    if not completed:
        return _as_orienteering_fallback(fallback)

    single_scores = [
        _orienteering_single_candidate_score(current, candidate, density_map, world, platform, planner)
        for candidate in candidates
    ]
    best_single_score = max(single_scores) if single_scores else fallback.expected_value
    best_beam: _OrienteeringBeam | None = None
    best_score = -np.inf
    min_route_points = max(1, planner.belief_orienteering_min_route_points)
    for beam in completed:
        if len(beam.route) < min_route_points:
            continue
        score = _orienteering_beam_score(beam, platform, planner)
        opportunity_loss = max(0.0, best_single_score - beam.first_leg_score)
        score -= planner.belief_orienteering_opportunity_cost_weight * opportunity_loss
        if score > best_score:
            best_score = score
            best_beam = beam

    if best_beam is None or not best_beam.route:
        return _as_orienteering_fallback(fallback)
    if best_score <= fallback.expected_value + planner.belief_orienteering_switch_margin:
        return _as_orienteering_fallback(fallback)

    details: dict[str, float | str] = {
        "candidate_type": best_beam.kinds[0],
        "planning_mode": "receding_orienteering",
        "score_total": float(best_score),
        "score_benefit": float(best_beam.benefit),
        "score_risk_penalty": float(best_beam.risk),
        "score_effort_m": float(best_beam.length_m),
        "score_expected_collection": float(best_beam.expected_collection),
        "score_rollout_collection": float(max(0.0, best_beam.expected_collection - _swept_expected_count(density_map, current, best_beam.route[0], platform))),
        "score_information_gain": float(best_beam.information_gain),
        "score_target_confirmation": float(best_beam.target_confirmation),
        "score_refine_bonus": 0.0,
        "score_empty_risk": 0.0,
        "score_stale_risk": 0.0,
        "score_path_cost": float(np.linalg.norm(best_beam.route[0] - current)),
        "orienteering_route_points": float(len(best_beam.route)),
        "orienteering_route_length_m": float(best_beam.length_m),
        "orienteering_best_single_score": float(best_single_score),
        "orienteering_first_leg_score": float(best_beam.first_leg_score),
        "orienteering_opportunity_loss": float(max(0.0, best_single_score - best_beam.first_leg_score)),
        "orienteering_fallback_score": float(fallback.expected_value),
    }
    return GoalDecision(
        best_beam.route[0].copy(),
        "belief_orienteering",
        "belief_orienteering_score",
        float(best_score),
        details,
    )


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
        return GoalDecision(
            state.current_route[0].copy(),
            state.current_route_mode,
            state.current_route_reason,
            1.0,
            dict(state.current_route_details),
        )
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
    if planner.mode == "belief_cluster_route":
        return next_belief_cluster_route(t_s, current, state, density_map, world, platform, planner, targets)
    if planner.mode in BELIEF_ORIENTEERING_MODES:
        return next_belief_orienteering(t_s, current, state, density_map, world, platform, planner, targets)
    if planner.mode in BELIEF_HORIZON_MODES:
        return next_belief_horizon(t_s, current, state, density_map, world, platform, planner, targets)
    if planner.mode == "confirmed_route":
        confirmed = targets.confirmed_targets(t_s)
        if confirmed:
            state.current_route = nearest_neighbor_route(current, confirmed, planner.route_batch_size)
            state.current_route_mode = "route"
            state.current_route_reason = "confirmed_target_route"
            state.current_route_details = {}
            if state.current_route:
                return GoalDecision(state.current_route[0].copy(), "route", "confirmed_target_route", 1.0)
        return GoalDecision(next_coverage(state), "coverage", "no_confirmed_targets", 0.0)

    active_reached = state.active_goal is not None and np.linalg.norm(state.active_goal - current) <= platform.arrival_tolerance_m
    if state.active_goal is None or active_reached or t_s - state.last_replan_t_s >= planner.replan_interval_s:
        state.last_replan_t_s = t_s
        state.active_goal = next_active(current, state, density_map, world, platform, planner)
    return GoalDecision(state.active_goal.copy(), "active", "active_entropy_density_score", 0.0)


def pop_route_goal_if_arrived(state: PlannerState, pos: np.ndarray, tolerance_m: float, targets: TargetQueue) -> None:
    if state.current_route and np.linalg.norm(state.current_route[0] - pos) <= tolerance_m:
        if state.current_route_mode == "route":
            targets.remove_near(pos, tolerance_m * 2.5)
        state.current_route.pop(0)
        if not state.current_route:
            state.current_route = None
            state.current_route_mode = "route"
            state.current_route_reason = "confirmed_target_route"
            state.current_route_details = {}
    if state.oracle_route and np.linalg.norm(state.oracle_route[0] - pos) <= tolerance_m:
        state.oracle_route.pop(0)
