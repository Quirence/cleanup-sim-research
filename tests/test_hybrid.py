from __future__ import annotations

import numpy as np
from dataclasses import replace

from cleanup_sim.config import GridConfig, PlannerConfig, scenario_config
from cleanup_sim.hybrid import HybridDecision, choose_hybrid_mode
from cleanup_sim.mapping import init_probability_map, make_grid
from cleanup_sim.planners import _score_candidate, next_active


def test_hybrid_routes_when_enough_confirmed_targets_and_low_entropy() -> None:
    planner = PlannerConfig(mode="hybrid", hybrid_min_confirmed_targets=3, hybrid_explore_entropy_threshold=0.2)
    decision = choose_hybrid_mode(mean_entropy=0.12, confirmed_target_count=3, planner=planner)
    assert decision == HybridDecision.ROUTE


def test_hybrid_explores_when_not_enough_targets() -> None:
    planner = PlannerConfig(mode="hybrid", hybrid_min_confirmed_targets=3, hybrid_explore_entropy_threshold=0.2)
    decision = choose_hybrid_mode(mean_entropy=0.12, confirmed_target_count=2, planner=planner)
    assert decision == HybridDecision.EXPLORE


def test_hybrid_explores_when_entropy_is_high_even_with_targets() -> None:
    planner = PlannerConfig(mode="hybrid", hybrid_min_confirmed_targets=3, hybrid_explore_entropy_threshold=0.2)
    decision = choose_hybrid_mode(mean_entropy=0.25, confirmed_target_count=5, planner=planner)
    assert decision == HybridDecision.EXPLORE


def test_active_ablation_modes_return_waypoints_inside_world() -> None:
    for mode in ["active_entropy", "active_probability", "active_no_distance"]:
        cfg = scenario_config("clustered_base", 0, mode)
        grid = make_grid(cfg.world, cfg.grid)
        prob_map = init_probability_map(grid, cfg.grid)
        point = next_active(np.array([10.0, 100.0]), 0.0, prob_map, cfg.world, cfg.planner, cfg.fusion)
        assert 0.0 <= point[0] <= cfg.world.width
        assert 0.0 <= point[1] <= cfg.world.height


def test_active_no_distance_removes_travel_penalty() -> None:
    active_cfg = scenario_config("clustered_base", 0, "active")
    no_distance_cfg = scenario_config("clustered_base", 0, "active_no_distance")
    grid = make_grid(active_cfg.world, active_cfg.grid)
    prob_map = init_probability_map(grid, active_cfg.grid)
    current = np.array([10.0, 10.0])
    far_point = np.array([190.0, 190.0])

    active_score = _score_candidate(
        far_point,
        current,
        0.0,
        prob_map,
        active_cfg.planner,
        active_cfg.fusion.radar,
    )
    no_distance_score = _score_candidate(
        far_point,
        current,
        0.0,
        prob_map,
        no_distance_cfg.planner,
        no_distance_cfg.fusion.radar,
    )

    assert no_distance_score > active_score


def test_active_score_is_stable_under_grid_resolution_change() -> None:
    cfg = scenario_config("clustered_base", 0, "active")
    coarse_cfg = replace(cfg, grid=GridConfig(nx=50, ny=50, prior=cfg.grid.prior))
    grid = make_grid(cfg.world, cfg.grid)
    coarse_grid = make_grid(coarse_cfg.world, coarse_cfg.grid)
    prob_map = init_probability_map(grid, cfg.grid)
    coarse_prob_map = init_probability_map(coarse_grid, coarse_cfg.grid)
    current = np.array([10.0, 100.0])
    point = np.array([100.0, 100.0])

    score = _score_candidate(point, current, 0.0, prob_map, cfg.planner, cfg.fusion.radar)
    coarse_score = _score_candidate(point, current, 0.0, coarse_prob_map, cfg.planner, cfg.fusion.radar)

    assert abs(score - coarse_score) / max(1.0, abs(score)) < 0.15
