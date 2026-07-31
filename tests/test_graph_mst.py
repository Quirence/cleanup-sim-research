from __future__ import annotations

from dataclasses import replace

import numpy as np

from cleanup_sim.config import scenario_config
from cleanup_sim.mapping import init_probability_map, make_grid
from cleanup_sim.planners import PlannerState, choose_next_goal, lawnmower_route, mst_route
from cleanup_sim.sensors import Detection
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
