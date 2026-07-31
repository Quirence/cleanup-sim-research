from __future__ import annotations

from dataclasses import replace

import numpy as np

from cleanup_sim.config import scenario_config
from cleanup_sim.mapping import init_probability_map, make_grid
from cleanup_sim.planners import (
    PlannerState,
    choose_next_goal,
    lawnmower_route,
    mst_route,
    nearest_neighbor_route,
    should_invalidate_graph_route,
)
from cleanup_sim.sensors import Detection
from cleanup_sim.simulation import run_simulation
from cleanup_sim.targets import TargetQueue


def test_mst_route_visits_each_target_exactly_once() -> None:
    start = np.array([0.0, 0.0])
    targets = [np.array([10.0, 0.0]), np.array([0.0, 10.0]), np.array([10.0, 10.0])]

    route = mst_route(start, targets)

    assert len(route) == len(targets)
    visited = {tuple(np.round(p, 6)) for p in route}
    expected = {tuple(np.round(p, 6)) for p in targets}
    assert visited == expected


def test_mst_route_orders_collinear_points_without_backtracking() -> None:
    start = np.array([0.0, 0.0])
    targets = [np.array([30.0, 0.0]), np.array([10.0, 0.0]), np.array([20.0, 0.0])]

    route = mst_route(start, targets)

    assert [float(p[0]) for p in route] == [10.0, 20.0, 30.0]


def test_mst_route_respects_limit() -> None:
    start = np.array([0.0, 0.0])
    targets = [np.array([10.0, 0.0]), np.array([20.0, 0.0]), np.array([30.0, 0.0])]

    route = mst_route(start, targets, limit=2)

    assert len(route) == 2


def test_mst_route_handles_empty_targets() -> None:
    assert mst_route(np.array([0.0, 0.0]), []) == []


def test_mst_route_differs_from_nearest_neighbor_on_branching_layout() -> None:
    start = np.array([0.0, 0.0])
    targets = [
        np.array([38.1, 43.0]),
        np.array([48.9, 97.6]),
        np.array([77.6, 30.9]),
        np.array([27.0, 86.3]),
        np.array([88.1, 51.1]),
    ]

    mst_order = [tuple(p) for p in mst_route(start, targets)]
    nn_order = [tuple(p) for p in nearest_neighbor_route(start, targets)]

    assert mst_order != nn_order


def _empty_target_queue(cfg) -> TargetQueue:
    return TargetQueue(
        confirm_prob=cfg.planner.detected_confirm_prob,
        confirm_hits=cfg.planner.target_confirm_hits,
        nms_radius_m=cfg.planner.detected_nms_radius_m,
        min_sensor_types=cfg.planner.target_min_sensor_types,
    )


def test_choose_next_goal_uses_mst_route_when_targets_confirmed() -> None:
    cfg = scenario_config("clustered_base", 0, "graph_mst")
    grid = make_grid(cfg.world, cfg.grid)
    prob_map = init_probability_map(grid, cfg.grid)
    state = PlannerState(coverage_route=lawnmower_route(cfg.world, cfg.planner))
    target_queue = _empty_target_queue(cfg)
    det = Detection(sensor="camera", position=np.array([50.0, 60.0]), confidence=0.9, source_index=None)
    det2 = Detection(sensor="radar", position=np.array([50.0, 60.0]), confidence=0.9, source_index=None)
    target_queue.add_detections([det], t=0.0, world=cfg.world)
    target_queue.add_detections([det2], t=1.0, world=cfg.world)
    assert target_queue.confirmed_targets()

    goal, label = choose_next_goal(
        t=0.0,
        current=np.array(cfg.world.depot, dtype=float),
        heading=0.0,
        state=state,
        prob_map=prob_map,
        world=cfg.world,
        robot=cfg.robot,
        planner=cfg.planner,
        fusion=cfg.fusion,
        target_queue=target_queue,
    )

    assert label == "route"
    assert np.allclose(goal, [50.0, 60.0], atol=1.0)


def test_choose_next_goal_falls_back_to_lawnmower_without_confirmed_targets() -> None:
    cfg = scenario_config("clustered_base", 0, "graph_mst")
    grid = make_grid(cfg.world, cfg.grid)
    prob_map = init_probability_map(grid, cfg.grid)
    route = lawnmower_route(cfg.world, cfg.planner)
    state = PlannerState(coverage_route=route)
    target_queue = _empty_target_queue(cfg)

    goal, label = choose_next_goal(
        t=0.0,
        current=np.array(cfg.world.depot, dtype=float),
        heading=0.0,
        state=state,
        prob_map=prob_map,
        world=cfg.world,
        robot=cfg.robot,
        planner=cfg.planner,
        fusion=cfg.fusion,
        target_queue=target_queue,
    )

    assert label == "coverage"
    assert np.allclose(goal, route[0])


def test_should_invalidate_graph_route_only_for_graph_mst_route_with_new_confirmations() -> None:
    assert should_invalidate_graph_route("graph_mst", "route", [object()]) is True
    assert should_invalidate_graph_route("graph_mst", "route", []) is False
    assert should_invalidate_graph_route("graph_mst", "coverage", [object()]) is False
    assert should_invalidate_graph_route("detected_tsp", "route", [object()]) is False


def test_graph_mst_mode_runs_full_simulation_and_records_route_events() -> None:
    cfg = scenario_config("clustered_base", 4, "graph_mst")
    cfg = replace(cfg, robot=replace(cfg.robot, tmax_s=1200.0))
    result = run_simulation(cfg)

    assert result.summary["mode"] == "graph_mst"
    assert np.all(result.belief >= 0.0)
    assert np.all(result.belief <= 1.0)
    events = set(result.events["event"].tolist()) if not result.events.empty else set()
    assert "target_confirmed" in events
    assert "target_routed" in events


def test_graph_mst_invalidation_hook_causes_route_churn_during_simulation() -> None:
    # When a new target is confirmed mid-route, should_invalidate_graph_route (wired into
    # simulation.py) clears the in-flight route so choose_next_goal replans immediately.
    # Each replan while still in "route" mode logs another "target_routed" event, but
    # target_route_attempts only counts routes that were followed all the way to arrival.
    # If the invalidation hook is actually firing, routes get abandoned and rebuilt before
    # arrival, so the number of "target_routed" events must exceed target_route_attempts.
    # If the hook were deleted (or never wired up), routes would only ever be replaced on
    # arrival, so target_routed events would equal target_route_attempts (plus at most the
    # initial coverage->route transitions), and this assertion would fail.
    cfg = scenario_config("clustered_base", 4, "graph_mst")
    cfg = replace(cfg, robot=replace(cfg.robot, tmax_s=1200.0))
    result = run_simulation(cfg)

    assert not result.events.empty
    n_target_routed = int((result.events["event"] == "target_routed").sum())
    target_route_attempts = result.summary["target_route_attempts"]

    assert n_target_routed > target_route_attempts


def test_run_experiments_parser_accepts_graph_mst_mode() -> None:
    from cleanup_sim.run_experiments import build_parser as build_experiments_parser

    args = build_experiments_parser().parse_args(["--modes", "graph_mst"])
    assert args.modes == ["graph_mst"]


def test_run_once_parser_accepts_graph_mst_mode() -> None:
    from cleanup_sim.run_once import build_parser as build_once_parser

    args = build_once_parser().parse_args(["--mode", "graph_mst"])
    assert args.mode == "graph_mst"


def test_graph_mst_excluded_from_default_experiment_modes() -> None:
    from cleanup_sim.run_experiments import DEFAULT_MODES

    assert "graph_mst" not in DEFAULT_MODES
