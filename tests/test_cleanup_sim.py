from __future__ import annotations

import numpy as np

from dataclasses import replace

from cleanup_sim.config import RobotConfig, scenario_config
from cleanup_sim.mapping import bayesian_update, entropy, init_probability_map, make_grid
from cleanup_sim.planners import PlannerState, lawnmower_route, next_lawnmower
from cleanup_sim.run_experiments import DEFAULT_MODES, aggregate_summary, build_parser
from cleanup_sim.sensors import visible_mask
from cleanup_sim.simulation import run_simulation


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


def test_scenario_config_accepts_hybrid_mode() -> None:
    cfg = scenario_config("clustered_base", 0, "hybrid")
    assert cfg.planner.mode == "hybrid"
    assert cfg.planner.hybrid_min_confirmed_targets >= 1
    assert 0.0 < cfg.planner.hybrid_switch_prob <= 1.0


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


def test_simulation_respects_max_path_budget() -> None:
    cfg = scenario_config("clustered_base", 1, "active")
    cfg = replace(cfg, robot=replace(cfg.robot, tmax_s=7200.0))
    cfg = replace(cfg, planner=replace(cfg.planner, max_path_m=500.0))

    result = run_simulation(cfg)

    assert result.summary["path_length_m"] <= 502.0
    assert result.summary["stop_reason"] in {"path_budget", "done"}


def test_default_experiment_modes_include_hybrid_and_ablations() -> None:
    assert "hybrid" in DEFAULT_MODES
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
    })

    aggregate = aggregate_summary(df)

    assert "target_confirmed_mean" in aggregate.columns
    assert "target_precision_mean" in aggregate.columns
