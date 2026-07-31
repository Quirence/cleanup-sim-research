from __future__ import annotations

import numpy as np

from dataclasses import replace

from cleanup_sim.config import RobotConfig, scenario_config
from cleanup_sim.mapping import bayesian_update, entropy, init_probability_map, make_grid
from cleanup_sim.planners import PlannerState, lawnmower_route, next_greedy, next_lawnmower, suppress_greedy_region
from cleanup_sim.run_experiments import DEFAULT_MODES, aggregate_summary, build_parser
from cleanup_sim.sensors import visible_mask
from cleanup_sim.simulation import _collected_near_goal, run_simulation
from cleanup_sim.world import DebrisField, true_occupancy


def test_entropy_maximum_near_half() -> None:
    values = np.array([0.01, 0.5, 0.99])
    h = entropy(values)
    assert h[1] > h[0]
    assert h[1] > h[2]


def test_bayesian_update_direction() -> None:
    prior = np.array([0.2])
    positive = bayesian_update(prior, np.array([True]), np.array([0.8]), np.array([0.05]))
    negative = bayesian_update(prior, np.array([False]), np.array([0.8]), np.array([0.05]))
    assert positive[0] > prior[0]
    assert negative[0] < prior[0]
    assert 0.0 <= positive[0] <= 1.0
    assert 0.0 <= negative[0] <= 1.0


def test_visible_mask_respects_range_and_fov() -> None:
    cfg = scenario_config("clustered_base", 0, "active")
    grid = make_grid(cfg.world, cfg.grid)
    pose = np.array([cfg.world.depot_x, cfg.world.depot_y, 0.0])
    mask, distance, bearing = visible_mask(grid, pose, cfg.fusion.camera)
    assert np.all(distance[mask] <= cfg.fusion.camera.range_m + 1e-9)
    assert np.all(np.abs(bearing[mask]) <= np.deg2rad(cfg.fusion.camera.fov_deg) * 0.5 + 1e-9)


def test_lawnmower_route_repeats_after_one_pass() -> None:
    cfg = scenario_config("clustered_base", 0, "lawnmower")
    route = lawnmower_route(cfg.world, cfg.planner)
    state = PlannerState(coverage_route=route)

    visited = [next_lawnmower(state) for _ in range(len(route) + 1)]

    assert np.allclose(visited[-1], route[0])


def test_lawnmower_dense_has_fair_collection_spacing() -> None:
    sparse = scenario_config("clustered_base", 0, "lawnmower_sparse")
    dense = scenario_config("clustered_base", 0, "lawnmower_dense")

    assert sparse.planner.coverage_spacing_m > 2.0 * sparse.robot.collect_radius_m
    assert dense.planner.coverage_spacing_m <= 2.0 * dense.robot.collect_radius_m
    assert len(lawnmower_route(dense.world, dense.planner)) > len(lawnmower_route(sparse.world, sparse.planner))


def test_true_occupancy_can_exclude_collected_debris() -> None:
    field = DebrisField(
        positions=np.array([[1.0, 1.0], [3.0, 3.0]]),
        masses=np.array([1.0, 1.0]),
        types=np.array(["plastic", "plastic"]),
        collected=np.array([True, False]),
    )
    edges = np.array([0.0, 2.0, 4.0])

    initial = true_occupancy(field, edges, edges)
    residual = true_occupancy(field, edges, edges, include_collected=False)

    assert int(initial.sum()) == 2
    assert int(residual.sum()) == 1


def test_collected_near_goal_detects_en_route_target_success() -> None:
    events = [{"x": 10.0, "y": 10.0}, {"x": 30.0, "y": 30.0}]

    assert _collected_near_goal(events, np.array([12.0, 10.0]), radius_m=3.0)
    assert not _collected_near_goal(events, np.array([20.0, 20.0]), radius_m=3.0)


def test_greedy_avoids_current_argmax_cell() -> None:
    cfg = scenario_config("clustered_base", 0, "greedy")
    grid = make_grid(cfg.world, cfg.grid)
    prob_map = init_probability_map(grid, cfg.grid)
    prob_map.belief.fill(0.1)
    prob_map.belief[10, 10] = 0.99
    prob_map.belief[20, 20] = 0.8
    current = np.array([grid.x_centers[10], grid.y_centers[10]])
    state = PlannerState(coverage_route=[])

    goal = next_greedy(prob_map, current, state, cfg.robot.collect_radius_m)

    assert np.allclose(goal, np.array([grid.x_centers[20], grid.y_centers[20]]))


def test_greedy_suppression_skips_visited_hotspot() -> None:
    cfg = scenario_config("clustered_base", 0, "greedy")
    grid = make_grid(cfg.world, cfg.grid)
    prob_map = init_probability_map(grid, cfg.grid)
    prob_map.belief.fill(0.1)
    prob_map.belief[30, 30] = 0.99
    prob_map.belief[70, 70] = 0.8
    state = PlannerState(coverage_route=[])
    visited = np.array([grid.x_centers[30], grid.y_centers[30]])

    suppress_greedy_region(state, prob_map, visited, cfg.robot.collect_radius_m)
    goal = next_greedy(prob_map, visited + np.array([20.0, 0.0]), state, cfg.robot.collect_radius_m)

    assert np.allclose(goal, np.array([grid.x_centers[70], grid.y_centers[70]]))


def test_probability_map_bounds_after_run() -> None:
    cfg = scenario_config("clustered_base", 3, "active")
    cfg = replace(cfg, robot=replace(cfg.robot, tmax_s=400.0))
    result = run_simulation(cfg)
    assert np.all(result.belief >= 0.0)
    assert np.all(result.belief <= 1.0)
    assert result.summary["mode"] == "active"


def test_reproducible_same_seed() -> None:
    cfg1 = scenario_config("uniform_base", 5, "greedy")
    cfg2 = scenario_config("uniform_base", 5, "greedy")
    cfg1 = replace(cfg1, robot=replace(cfg1.robot, tmax_s=300.0))
    cfg2 = replace(cfg2, robot=replace(cfg2.robot, tmax_s=300.0))
    r1 = run_simulation(cfg1)
    r2 = run_simulation(cfg2)
    assert r1.summary["collected"] == r2.summary["collected"]
    assert np.isclose(r1.summary["path_length_m"], r2.summary["path_length_m"])
    assert np.allclose(r1.path, r2.path)


def test_greedy_smoke_uses_path_budget_instead_of_stalling() -> None:
    cfg = scenario_config("uniform_base", 5, "greedy")
    cfg = replace(cfg, robot=replace(cfg.robot, tmax_s=1000.0))
    cfg = replace(cfg, planner=replace(cfg.planner, max_path_m=500.0))

    result = run_simulation(cfg)

    assert result.summary["stop_reason"] in {"path_budget", "done"}
    assert result.summary["path_length_m"] >= 490.0 or result.summary["stop_reason"] == "done"


def test_scenario_config_accepts_hybrid_mode() -> None:
    cfg = scenario_config("clustered_base", 0, "hybrid")
    assert cfg.planner.mode == "hybrid"
    assert cfg.planner.hybrid_min_confirmed_targets >= 1
    assert 0.0 < cfg.planner.hybrid_explore_entropy_threshold < 1.0


def test_scenario_config_accepts_ablation_modes() -> None:
    for mode in ["active_entropy", "active_probability", "active_no_distance"]:
        cfg = scenario_config("clustered_base", 0, mode)
        assert cfg.planner.mode == mode


def test_detected_tsp_records_detection_before_target_routing() -> None:
    cfg = scenario_config("clustered_base", 4, "detected_tsp")
    cfg = replace(cfg, robot=replace(cfg.robot, tmax_s=1200.0))
    result = run_simulation(cfg)

    events = result.events["event"].tolist() if not result.events.empty else []
    assert "detect" in events
    assert result.summary["mode"] == "detected_tsp"


def test_target_route_visit_metrics_are_recorded_for_detected_tsp() -> None:
    cfg = scenario_config("clustered_base", 4, "detected_tsp")
    cfg = replace(cfg, robot=replace(cfg.robot, tmax_s=1200.0))
    result = run_simulation(cfg)

    assert "target_route_attempts" in result.summary
    assert "target_visit_successes" in result.summary
    assert "target_visit_false" in result.summary
    assert "target_precision" in result.summary
    assert result.summary["false_visits"] == result.summary["target_visit_false"]
    assert result.summary["target_route_attempts"] >= (
        result.summary["target_visit_successes"] + result.summary["target_visit_false"]
    )


def test_target_events_are_recorded_for_route_based_planner() -> None:
    cfg = scenario_config("clustered_base", 4, "detected_tsp")
    cfg = replace(cfg, robot=replace(cfg.robot, tmax_s=1200.0))
    result = run_simulation(cfg)

    events = set(result.events["event"].tolist()) if not result.events.empty else set()
    assert "target_confirmed" in events
    assert "target_routed" in events
    assert {"target_visit_success", "target_visit_false"} & events


def test_hybrid_mode_runs_and_records_planner_decisions() -> None:
    cfg = scenario_config("clustered_base", 2, "hybrid")
    cfg = replace(cfg, robot=replace(cfg.robot, tmax_s=800.0))
    result = run_simulation(cfg)

    assert result.summary["mode"] == "hybrid"
    assert np.all(result.belief >= 0.0)
    assert np.all(result.belief <= 1.0)
    assert "planner_mode" in result.series.columns
    assert set(result.series["planner_mode"].dropna()).issubset({"explore", "route", "return"})


def test_active_mode_does_not_fallback_to_greedy_between_replans() -> None:
    cfg = scenario_config("clustered_base", 2, "active")
    cfg = replace(cfg, robot=replace(cfg.robot, tmax_s=900.0))
    cfg = replace(cfg, planner=replace(cfg.planner, max_path_m=800.0))

    result = run_simulation(cfg)

    assert "planner_mode" in result.series.columns
    assert "greedy" not in set(result.series["planner_mode"].dropna())
    assert set(result.series["planner_mode"].dropna()).issubset({"active", "return"})


def test_simulation_respects_max_path_budget() -> None:
    cfg = scenario_config("clustered_base", 1, "active")
    cfg = replace(cfg, robot=replace(cfg.robot, tmax_s=7200.0))
    cfg = replace(cfg, planner=replace(cfg.planner, max_path_m=500.0))

    result = run_simulation(cfg)

    assert result.summary["path_length_m"] <= 502.0
    assert result.summary["stop_reason"] in {"path_budget", "done"}


def test_default_experiment_modes_include_hybrid_and_ablations() -> None:
    assert "hybrid" in DEFAULT_MODES
    assert "lawnmower_sparse" in DEFAULT_MODES
    assert "lawnmower_dense" in DEFAULT_MODES
    assert "active_entropy" in DEFAULT_MODES
    assert "active_probability" in DEFAULT_MODES
    assert "active_no_distance" in DEFAULT_MODES


def test_experiment_parser_accepts_smoke_budget_overrides() -> None:
    args = build_parser().parse_args(["--tmax-s", "120", "--max-path-m", "300"])
    assert args.tmax_s == 120
    assert args.max_path_m == 300


def test_aggregate_summary_includes_target_metrics() -> None:
    import pandas as pd

    df = pd.DataFrame({
        "scenario": ["s", "s"],
        "mode": ["hybrid", "hybrid"],
        "target_confirmed": [3, 5],
        "target_route_attempts": [2, 4],
        "target_visit_successes": [1, 2],
        "target_visit_false": [1, 2],
        "target_precision": [0.5, 0.5],
        "path_to_80_m": [100.0, None],
    })

    aggregate = aggregate_summary(df)

    assert "target_confirmed_mean" in aggregate.columns
    assert "target_precision_mean" in aggregate.columns
    assert "path_to_80_m_reach_rate" in aggregate.columns
    assert aggregate.loc[0, "path_to_80_m_reach_rate"] == 0.5
