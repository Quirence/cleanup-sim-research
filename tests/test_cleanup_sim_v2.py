from __future__ import annotations

from dataclasses import replace

import numpy as np

from cleanup_sim_v2.collection import aperture_candidates, collect_in_aperture
from cleanup_sim_v2.config import (
    HydroConfig,
    PlatformConfig,
    SensorConfig,
    SensorSuiteConfig,
    WorldConfig,
    scenario_config,
)
from cleanup_sim_v2.io import config_hash
from cleanup_sim_v2.hydrodynamics import drift_debris
from cleanup_sim_v2.planners import make_coverage_route
from cleanup_sim_v2.run_experiments import ALL_MODES, BASELINE_MODES, build_parser as build_experiment_parser
from cleanup_sim_v2.sensors import Detection, detect_with_sensor
from cleanup_sim_v2.simulation import run_simulation
from cleanup_sim_v2.targets import TargetQueue
from cleanup_sim_v2.world import DebrisField, make_debris_field


def _field_at(points: list[tuple[float, float]]) -> DebrisField:
    positions = np.array(points, dtype=float)
    n = len(points)
    return DebrisField(
        positions=positions.copy(),
        initial_positions=positions.copy(),
        masses_kg=np.full(n, 0.2),
        sizes_m=np.full(n, 0.2),
        types=np.array(["plastic"] * n),
        collected=np.zeros(n, dtype=bool),
        missed_attempts=np.zeros(n, dtype=int),
        pushed_events=np.zeros(n, dtype=int),
        capture_progress_kg=np.zeros(n, dtype=float),
    )


def test_collection_impossible_outside_front_aperture() -> None:
    field = _field_at([(1.0, 1.2), (-0.5, 0.0)])
    platform = PlatformConfig(collection_width_m=1.0, collection_length_m=1.5)
    ids = aperture_candidates(field, np.array([0.0, 0.0]), np.array([1.0, 0.0]), 0.0, platform)
    assert ids.size == 0


def test_object_can_be_detected_but_not_collected() -> None:
    rng = np.random.default_rng(1)
    field = _field_at([(10.0, 0.0)])
    sensor = SensorConfig(
        name="camera",
        range_m=20.0,
        fov_deg=90.0,
        p_detect_max=1.0,
        decay_range_m=1e9,
        min_detectable_size_m=0.01,
        localization_sigma_m=0.0,
        localization_sigma_per_m=0.0,
        clutter_rate_per_m2=0.0,
        confidence_sigma=0.0,
    )
    detections = detect_with_sensor(rng, field, WorldConfig(), np.array([0.0, 0.0, 0.0]), sensor)
    assert len(detections) == 1
    events, _ = collect_in_aperture(
        rng,
        field,
        np.array([0.0, 0.0]),
        np.array([1.0, 0.0]),
        0.0,
        PlatformConfig(collection_width_m=1.0, collection_length_m=1.0),
        0.0,
        1.0,
    )
    assert events == []
    assert not field.collected[0]


def test_reached_object_can_miss_capture() -> None:
    rng = np.random.default_rng(2)
    field = _field_at([(0.8, 0.0)])
    platform = PlatformConfig(collection_width_m=1.0, collection_length_m=1.0, capture_probability=0.0, capture_time_s=0.0)
    events, load = collect_in_aperture(
        rng,
        field,
        np.array([0.0, 0.0]),
        np.array([1.0, 0.0]),
        0.0,
        platform,
        0.0,
        1.0,
    )
    assert len(events) == 1
    assert events[0].reason == "missed_capture"
    assert not events[0].success
    assert not field.collected[0]
    assert load == 0.0


def test_heavy_object_can_be_collected_after_accumulated_contact() -> None:
    rng = np.random.default_rng(22)
    field = _field_at([(0.5, 0.0)])
    field.masses_kg[0] = 2.0
    platform = PlatformConfig(
        collection_width_m=1.0,
        collection_length_m=1.0,
        collection_throughput_kg_s=1.0,
        capture_time_s=0.0,
        capture_probability=1.0,
    )
    first_events, load = collect_in_aperture(
        rng,
        field,
        np.array([0.0, 0.0]),
        np.array([1.0, 0.0]),
        0.0,
        platform,
        0.0,
        1.0,
    )
    assert first_events[0].reason == "partial_contact"
    assert not field.collected[0]

    second_events, load = collect_in_aperture(
        rng,
        field,
        np.array([0.0, 0.0]),
        np.array([1.0, 0.0]),
        0.0,
        platform,
        load,
        1.0,
    )
    assert second_events[-1].success
    assert field.collected[0]
    assert load == 2.0


def test_drift_is_reproducible_for_same_seed() -> None:
    world = WorldConfig(distribution="uniform", n_debris=5)
    base_rng = np.random.default_rng(3)
    field_a = make_debris_field(base_rng, world)
    field_b = DebrisField(
        positions=field_a.positions.copy(),
        initial_positions=field_a.initial_positions.copy(),
        masses_kg=field_a.masses_kg.copy(),
        sizes_m=field_a.sizes_m.copy(),
        types=field_a.types.copy(),
        collected=field_a.collected.copy(),
        missed_attempts=field_a.missed_attempts.copy(),
        pushed_events=field_a.pushed_events.copy(),
        capture_progress_kg=field_a.capture_progress_kg.copy(),
    )
    hydro = HydroConfig(current_x_mps=0.05, wind_x_mps=2.0, windage=0.01, diffusivity_m2_s=0.04)
    drift_debris(np.random.default_rng(10), field_a, world, hydro, 1.0)
    drift_debris(np.random.default_rng(10), field_b, world, hydro, 1.0)
    assert np.allclose(field_a.positions, field_b.positions)


def test_robot_repulsion_keeps_positions_finite_and_bounded() -> None:
    rng = np.random.default_rng(4)
    world = WorldConfig(width_m=20.0, height_m=20.0)
    field = _field_at([(10.5, 10.0), (19.8, 19.8)])
    hydro = HydroConfig(robot_repulsion_enabled=True, robot_repulsion_radius_m=3.0, robot_repulsion_gain_mps=2.0)
    drift_debris(rng, field, world, hydro, 1.0, robot_pos=np.array([10.0, 10.0]))
    assert np.isfinite(field.positions).all()
    assert np.all(field.positions[:, 0] >= 0.0)
    assert np.all(field.positions[:, 0] <= world.width_m)
    assert int(field.pushed_events.sum()) >= 1


def test_greedy_gets_empty_goal_metrics_like_other_modes() -> None:
    cfg = scenario_config("static_calm", 5, "greedy")
    zero_detection_sensor = SensorConfig(
        name="camera",
        range_m=1.0,
        fov_deg=1.0,
        p_detect_max=0.0,
        decay_range_m=1.0,
        min_detectable_size_m=1.0,
        localization_sigma_m=0.0,
        localization_sigma_per_m=0.0,
        clutter_rate_per_m2=0.0,
        confidence_sigma=0.0,
    )
    cfg = replace(
        cfg,
        world=WorldConfig(width_m=40.0, height_m=40.0, depot_x_m=10.0, depot_y_m=10.0, n_debris=1, distribution="uniform"),
        platform=replace(cfg.platform, tmax_s=300.0, max_path_m=100.0),
        sensors=SensorSuiteConfig(camera=zero_detection_sensor, radar=replace(zero_detection_sensor, name="radar")),
    )
    result = run_simulation(cfg)
    assert result.summary["mode"] == "greedy"
    assert result.summary["empty_goal_arrivals"] > 0
    assert result.summary["wasted_path_to_empty_goals"] > 0.0


def test_lawnmower_survey_and_collect_have_different_physical_spacing() -> None:
    survey = scenario_config("static_calm", 0, "lawnmower_survey")
    collect = scenario_config("static_calm", 0, "lawnmower_collect")
    assert survey.planner.coverage_spacing_m > collect.platform.collection_width_m
    assert collect.planner.coverage_spacing_m <= collect.platform.collection_width_m


def test_lawnmower_route_uses_transect_endpoints_not_grid_waypoints() -> None:
    cfg = scenario_config("static_calm", 0, "lawnmower_survey")
    route = make_coverage_route(cfg.world, cfg.planner)
    assert len(route) % 2 == 0
    assert np.allclose(route[0], [cfg.planner.coverage_margin_m, cfg.planner.coverage_margin_m])
    assert np.isclose(route[1][0], cfg.world.width_m - cfg.planner.coverage_margin_m)
    assert np.isclose(route[0][1], route[1][1])


def test_v2_baseline_parser_accepts_named_lawnmower_modes() -> None:
    args = build_experiment_parser().parse_args(["--baseline-only", "--seeds", "1"])
    assert args.baseline_only is True
    assert "lawnmower_survey" in BASELINE_MODES
    assert "lawnmower_collect" in BASELINE_MODES


def test_v2_parser_accepts_oracle_modes() -> None:
    args = build_experiment_parser().parse_args(["--modes", "greedy", "oracle_current_physics", "--seeds", "1"])
    assert args.modes == ["greedy", "oracle_current_physics"]
    assert "oracle_route_heuristic" in ALL_MODES


def test_config_hash_changes_when_significant_parameter_changes() -> None:
    cfg = scenario_config("static_calm", 0, "greedy")
    changed = replace(cfg, platform=replace(cfg.platform, collection_width_m=cfg.platform.collection_width_m + 0.1))
    assert config_hash(cfg.to_dict()) != config_hash(changed.to_dict())


def test_v2_target_queue_hides_source_ids_from_planner_tracks() -> None:
    cfg = scenario_config("static_calm", 0, "confirmed_route")
    queue = TargetQueue(cfg.planner)
    det = Detection("camera", np.array([20.0, 30.0]), 0.9, source_index=7, is_false=False, range_m=12.0)
    queue.add_detections([det, det], 0.0, cfg.world)
    assert len(queue.confirmed_targets(0.0)) == 1
    assert queue.tracks[0].source_ids == set()


def test_v2_target_queue_suppresses_empty_goal_region() -> None:
    cfg = scenario_config("static_calm", 0, "confirmed_route")
    queue = TargetQueue(cfg.planner)
    det = Detection("radar", np.array([40.0, 40.0]), 0.9, source_index=None, is_false=True, range_m=20.0)
    queue.add_detections([det, det], 0.0, cfg.world)
    assert len(queue.confirmed_targets(0.0)) == 1
    removed = queue.suppress_near(np.array([40.0, 40.0]), 10.0)
    queue.add_detections([det, det], 20.0, cfg.world)
    assert removed == 1
    assert queue.confirmed_targets(20.0) == []
