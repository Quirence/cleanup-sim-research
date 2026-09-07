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
    belief_scout_spacing_m,
    scenario_config,
    survey_lawnmower_spacing_m,
)
from cleanup_sim_v2.io import config_hash
from cleanup_sim_v2.hydrodynamics import drift_debris
from cleanup_sim_v2.mapping import init_density_map, make_grid
from cleanup_sim_v2.planners import (
    _approach_aware_candidates,
    _belief_candidates,
    _passes_density_risk_gate,
    _swept_expected_count,
    choose_goal,
    initial_state,
    make_coverage_route,
)
from cleanup_sim_v2.run_experiments import ALL_MODES, BASELINE_MODES, build_parser as build_experiment_parser
from cleanup_sim_v2.sensors import Detection, detect_with_sensor
from cleanup_sim_v2.simulation import (
    _motion_speed,
    _retarget_track_policy,
    _true_local_stats,
    _true_swept_count,
    run_simulation,
)
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


def test_belief_modes_use_radar_scale_scout_spacing() -> None:
    survey = scenario_config("static_calm", 0, "lawnmower_survey")
    belief = scenario_config("static_calm", 0, "belief_horizon")

    assert np.isclose(survey.planner.coverage_spacing_m, survey_lawnmower_spacing_m(survey.sensors))
    assert np.isclose(belief.planner.coverage_spacing_m, belief_scout_spacing_m(belief.sensors))
    assert belief.planner.coverage_spacing_m > survey.planner.coverage_spacing_m


def test_lawnmower_route_uses_transect_endpoints_not_grid_waypoints() -> None:
    cfg = scenario_config("static_calm", 0, "lawnmower_survey")
    route = make_coverage_route(cfg.world, cfg.planner)
    assert len(route) % 2 == 0
    y_values = np.arange(
        cfg.planner.coverage_margin_m,
        cfg.world.height_m - cfg.planner.coverage_margin_m + 1e-9,
        cfg.planner.coverage_spacing_m,
    )
    nearest_y = y_values[int(np.argmin(np.abs(y_values - cfg.world.depot_y_m)))]
    assert np.allclose(route[0], [cfg.planner.coverage_margin_m, nearest_y])
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


def test_v2_parser_accepts_belief_horizon_mode() -> None:
    args = build_experiment_parser().parse_args(
        ["--modes", "belief_horizon", "belief_horizon_density_risk_gate", "--seeds", "1"]
    )
    assert args.modes == ["belief_horizon", "belief_horizon_density_risk_gate"]
    assert "belief_horizon" in ALL_MODES
    assert "belief_horizon_density_risk_gate" in ALL_MODES


def test_v2_parser_accepts_belief_provisional_modes() -> None:
    modes = ["belief_horizon_provisional", "belief_orienteering_provisional"]
    args = build_experiment_parser().parse_args(["--modes", *modes, "--seeds", "1"])
    assert args.modes == modes
    for mode in modes:
        assert mode in ALL_MODES


def test_v2_parser_accepts_belief_cluster_route_mode() -> None:
    args = build_experiment_parser().parse_args(["--modes", "belief_cluster_route", "--seeds", "1"])
    assert args.modes == ["belief_cluster_route"]
    assert "belief_cluster_route" in ALL_MODES


def test_v2_parser_accepts_belief_orienteering_mode() -> None:
    args = build_experiment_parser().parse_args(["--modes", "belief_orienteering", "--seeds", "1"])
    assert args.modes == ["belief_orienteering"]
    assert "belief_orienteering" in ALL_MODES


def test_v2_parser_accepts_belief_orienteering_ablation_modes() -> None:
    modes = [
        "belief_orienteering_depth1",
        "belief_orienteering_no_opportunity_cost",
        "belief_orienteering_density_disabled",
    ]
    args = build_experiment_parser().parse_args(["--modes", *modes, "--seeds", "1"])
    assert args.modes == modes
    for mode in modes:
        assert mode in ALL_MODES


def test_v2_parser_accepts_belief_horizon_ablation_modes() -> None:
    modes = [
        "belief_horizon_approach_aware",
        "belief_horizon_retarget",
        "belief_horizon_retarget_strict",
        "belief_horizon_retarget_locked",
        "belief_horizon_retarget_region",
        "belief_horizon_retarget_drift_switch",
        "belief_horizon_no_efficiency",
        "belief_horizon_no_track_prediction",
        "belief_horizon_no_refinement",
    ]
    args = build_experiment_parser().parse_args(["--modes", *modes, "--seeds", "1"])
    assert args.modes == modes
    for mode in modes:
        assert mode in ALL_MODES


def test_v2_parser_accepts_checkpoint_resume_flags() -> None:
    args = build_experiment_parser().parse_args(["--modes", "belief_horizon", "--checkpoint", "--resume"])
    assert args.checkpoint is True
    assert args.resume is True


def test_v2_parser_accepts_uniform_distribution_scenarios() -> None:
    args = build_experiment_parser().parse_args(
        ["--scenarios", "uniform_static_calm", "uniform_weak_drift", "--modes", "greedy"]
    )
    assert args.scenarios == ["uniform_static_calm", "uniform_weak_drift"]


def test_v2_uniform_scenario_changes_distribution_but_preserves_hydro_case() -> None:
    clustered = scenario_config("weak_drift", 0, "greedy")
    uniform = scenario_config("uniform_weak_drift", 0, "greedy")

    assert clustered.world.distribution == "clustered"
    assert uniform.world.distribution == "uniform"
    assert uniform.hydro.current_x_mps == clustered.hydro.current_x_mps
    assert uniform.hydro.current_y_mps == clustered.hydro.current_y_mps
    assert uniform.hydro.diffusivity_m2_s == clustered.hydro.diffusivity_m2_s


def test_belief_horizon_ablation_modes_change_exact_component() -> None:
    base = scenario_config("weak_drift", 0, "belief_horizon")
    approach_aware = scenario_config("weak_drift", 0, "belief_horizon_approach_aware")
    risk_gated = scenario_config("weak_drift", 0, "belief_horizon_density_risk_gate")
    retarget = scenario_config("weak_drift", 0, "belief_horizon_retarget")
    retarget_strict = scenario_config("weak_drift", 0, "belief_horizon_retarget_strict")
    retarget_locked = scenario_config("weak_drift", 0, "belief_horizon_retarget_locked")
    retarget_region = scenario_config("weak_drift", 0, "belief_horizon_retarget_region")
    retarget_drift_switch = scenario_config("weak_drift", 0, "belief_horizon_retarget_drift_switch")
    no_efficiency = scenario_config("weak_drift", 0, "belief_horizon_no_efficiency")
    no_prediction = scenario_config("weak_drift", 0, "belief_horizon_no_track_prediction")
    no_refinement = scenario_config("weak_drift", 0, "belief_horizon_no_refinement")

    assert base.planner.belief_efficiency_score is True
    assert base.planner.belief_density_risk_gate_enabled is False
    assert base.planner.belief_approach_aware_enabled is False

    assert approach_aware.planner.belief_approach_aware_enabled is True
    assert approach_aware.planner.belief_density_risk_gate_enabled is False
    assert approach_aware.planner.belief_efficiency_score is True

    assert risk_gated.planner.belief_density_risk_gate_enabled is True
    assert risk_gated.planner.belief_approach_aware_enabled is False
    assert risk_gated.planner.belief_efficiency_score is True
    assert risk_gated.planner.belief_track_prediction_enabled is True
    assert risk_gated.planner.belief_refinement_enabled is True

    assert retarget.planner.belief_goal_retarget_enabled is True
    assert retarget.planner.belief_approach_aware_enabled is False
    assert retarget.planner.belief_density_risk_gate_enabled is False

    assert retarget_strict.planner.belief_goal_retarget_enabled is True
    assert retarget_strict.planner.belief_goal_retarget_max_extra_travel_m < retarget.planner.belief_goal_retarget_max_extra_travel_m
    assert retarget_strict.planner.belief_goal_retarget_score_tolerance < retarget.planner.belief_goal_retarget_score_tolerance
    assert retarget_strict.planner.belief_goal_retarget_require_same_track is False

    assert retarget_locked.planner.belief_goal_retarget_enabled is True
    assert retarget_locked.planner.belief_goal_retarget_max_extra_travel_m == retarget_strict.planner.belief_goal_retarget_max_extra_travel_m
    assert retarget_locked.planner.belief_goal_retarget_score_tolerance == retarget_strict.planner.belief_goal_retarget_score_tolerance
    assert retarget_locked.planner.belief_goal_retarget_require_same_track is True
    assert retarget_locked.planner.belief_goal_retarget_region_adaptive is False
    assert retarget_locked.planner.belief_goal_retarget_drift_switch is False

    assert retarget_region.planner.belief_goal_retarget_enabled is True
    assert retarget_region.planner.belief_goal_retarget_require_same_track is False
    assert retarget_region.planner.belief_goal_retarget_region_adaptive is True
    assert retarget_region.planner.belief_goal_retarget_drift_switch is False
    assert retarget_region.planner.belief_goal_retarget_region_radius_m < retarget_region.planner.belief_goal_retarget_max_shift_m

    assert retarget_drift_switch.planner.belief_goal_retarget_enabled is True
    assert retarget_drift_switch.planner.belief_goal_retarget_max_extra_travel_m == retarget_strict.planner.belief_goal_retarget_max_extra_travel_m
    assert retarget_drift_switch.planner.belief_goal_retarget_score_tolerance == retarget_strict.planner.belief_goal_retarget_score_tolerance
    assert retarget_drift_switch.planner.belief_goal_retarget_require_same_track is False
    assert retarget_drift_switch.planner.belief_goal_retarget_region_adaptive is False
    assert retarget_drift_switch.planner.belief_goal_retarget_drift_switch is True

    assert no_efficiency.planner.belief_efficiency_score is False
    assert no_efficiency.planner.belief_track_prediction_enabled is True
    assert no_efficiency.planner.belief_refinement_enabled is True

    assert base.planner.belief_track_prediction_enabled is True
    assert no_prediction.planner.belief_track_prediction_enabled is False
    assert no_prediction.planner.belief_efficiency_score is True
    assert no_prediction.planner.belief_refinement_enabled is True

    assert base.planner.belief_refinement_enabled is True
    assert no_refinement.planner.belief_refinement_enabled is False
    assert no_refinement.planner.belief_efficiency_score is True
    assert no_refinement.planner.belief_track_prediction_enabled is True


def test_belief_provisional_modes_enable_only_provisional_targets() -> None:
    base_horizon = scenario_config("weak_drift", 0, "belief_horizon")
    provisional_horizon = scenario_config("weak_drift", 0, "belief_horizon_provisional")
    base_orienteering = scenario_config("weak_drift", 0, "belief_orienteering")
    provisional_orienteering = scenario_config("weak_drift", 0, "belief_orienteering_provisional")

    assert base_horizon.planner.belief_provisional_targets_enabled is False
    assert provisional_horizon.planner.belief_provisional_targets_enabled is True
    assert provisional_horizon.planner.belief_provisional_require_camera is True
    assert provisional_horizon.planner.belief_track_prediction_enabled == base_horizon.planner.belief_track_prediction_enabled
    assert provisional_horizon.planner.belief_refinement_enabled == base_horizon.planner.belief_refinement_enabled

    assert base_orienteering.planner.belief_provisional_targets_enabled is False
    assert provisional_orienteering.planner.belief_provisional_targets_enabled is True
    assert provisional_orienteering.planner.belief_orienteering_depth == base_orienteering.planner.belief_orienteering_depth


def test_belief_orienteering_ablation_modes_change_exact_component() -> None:
    base = scenario_config("weak_drift", 0, "belief_orienteering")
    depth1 = scenario_config("weak_drift", 0, "belief_orienteering_depth1")
    no_opportunity = scenario_config("weak_drift", 0, "belief_orienteering_no_opportunity_cost")
    density_disabled = scenario_config("weak_drift", 0, "belief_orienteering_density_disabled")

    assert base.planner.belief_orienteering_depth == 3
    assert base.planner.belief_orienteering_min_route_points == 2
    assert base.planner.belief_orienteering_opportunity_cost_weight > 0.0
    assert base.planner.belief_orienteering_density_enabled is True

    assert depth1.planner.belief_orienteering_depth == 1
    assert depth1.planner.belief_orienteering_min_route_points == 1
    assert depth1.planner.belief_orienteering_opportunity_cost_weight == base.planner.belief_orienteering_opportunity_cost_weight
    assert depth1.planner.belief_orienteering_density_enabled is True

    assert no_opportunity.planner.belief_orienteering_depth == base.planner.belief_orienteering_depth
    assert no_opportunity.planner.belief_orienteering_min_route_points == base.planner.belief_orienteering_min_route_points
    assert no_opportunity.planner.belief_orienteering_opportunity_cost_weight == 0.0
    assert no_opportunity.planner.belief_orienteering_density_enabled is True

    assert density_disabled.planner.belief_orienteering_depth == base.planner.belief_orienteering_depth
    assert density_disabled.planner.belief_orienteering_opportunity_cost_weight == base.planner.belief_orienteering_opportunity_cost_weight
    assert density_disabled.planner.belief_orienteering_density_enabled is False


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


def test_v2_target_queue_assigns_stable_track_ids() -> None:
    cfg = scenario_config("static_calm", 0, "belief_horizon")
    queue = TargetQueue(cfg.planner)
    first = Detection("camera", np.array([20.0, 30.0]), 0.9, source_index=None, is_false=False, range_m=12.0)
    nearby = Detection("radar", np.array([20.5, 30.2]), 0.9, source_index=None, is_false=False, range_m=12.0)
    second = Detection("camera", np.array([45.0, 30.0]), 0.9, source_index=None, is_false=False, range_m=12.0)

    queue.add_detections([first], 0.0, cfg.world)
    assert queue.tracks[0].track_id == 1
    queue.add_detections([nearby], 1.0, cfg.world)
    assert len(queue.tracks) == 1
    assert queue.tracks[0].track_id == 1
    queue.add_detections([second], 2.0, cfg.world)

    assert [track.track_id for track in queue.tracks] == [1, 2]


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


def test_v2_target_queue_predicts_track_drift_and_uncertainty() -> None:
    cfg = scenario_config("weak_drift", 0, "confirmed_route")
    queue = TargetQueue(cfg.planner)
    det = Detection(
        "camera",
        np.array([20.0, 30.0]),
        0.9,
        source_index=None,
        is_false=False,
        range_m=8.0,
        localization_sigma_m=0.7,
    )
    queue.add_detections([det, det], 0.0, cfg.world)
    before = queue.tracks[0].position.copy()
    sigma_before = queue.tracks[0].localization_sigma_m
    hydro = HydroConfig(current_x_mps=0.1, current_y_mps=-0.05, diffusivity_m2_s=0.02)

    queue.predict(hydro, cfg.world, 10.0)

    assert np.allclose(queue.tracks[0].position, before + np.array([1.0, -0.5]))
    assert queue.tracks[0].localization_sigma_m > sigma_before


def test_belief_horizon_scores_swept_density_without_truth_access() -> None:
    cfg = scenario_config("static_calm", 0, "belief_horizon")
    cfg = replace(
        cfg,
        world=WorldConfig(width_m=60.0, height_m=40.0, depot_x_m=5.0, depot_y_m=20.0, n_debris=1),
        platform=replace(cfg.platform, collection_width_m=2.0, collection_length_m=2.0),
        grid=replace(cfg.grid, nx=30, ny=20),
    )
    grid = make_grid(cfg.world, cfg.grid)
    density_map = init_density_map(grid, cfg.grid, cfg.world)
    density_map.expected_count *= 0.0
    density_map.expected_count[
        (np.abs(grid.yy - 20.0) <= 1.0)
        & (grid.xx >= 15.0)
        & (grid.xx <= 40.0)
    ] = 1.0
    target_queue = TargetQueue(cfg.planner)
    decision = choose_goal(
        0.0,
        np.array(cfg.world.depot, dtype=float),
        initial_state(cfg.world, cfg.planner),
        density_map,
        cfg.world,
        cfg.platform,
        cfg.planner,
        target_queue,
        field=None,
    )

    assert decision.mode == "belief_horizon"
    assert decision.details["score_expected_collection"] > 0.0
    assert decision.details["candidate_type"] in {"density_peak", "density_transect", "entropy_peak"}


def test_belief_horizon_uses_coverage_when_prior_has_no_density_signal() -> None:
    cfg = scenario_config("static_calm", 0, "belief_horizon")
    grid = make_grid(cfg.world, cfg.grid)
    density_map = init_density_map(grid, cfg.grid, cfg.world)
    start = np.array(cfg.world.depot, dtype=float)

    decision = choose_goal(
        0.0,
        start,
        initial_state(cfg.world, cfg.planner),
        density_map,
        cfg.world,
        cfg.platform,
        cfg.planner,
        TargetQueue(cfg.planner),
        field=None,
    )

    assert decision.mode == "belief_horizon"
    assert decision.details["candidate_type"] in {"coverage_route", "coverage_fallback"}
    assert abs(decision.point[1] - start[1]) <= cfg.planner.coverage_spacing_m


def test_belief_horizon_prefers_pass_through_transect_when_density_continues_beyond_peak() -> None:
    cfg = scenario_config("static_calm", 0, "belief_horizon")
    cfg = replace(
        cfg,
        world=WorldConfig(width_m=60.0, height_m=40.0, depot_x_m=5.0, depot_y_m=20.0, n_debris=1),
        platform=replace(cfg.platform, collection_width_m=2.5, collection_length_m=1.8),
        planner=replace(
            cfg.planner,
            belief_candidate_count=4,
            belief_density_peak_count=1,
            belief_entropy_peak_count=0,
            belief_transect_count=1,
            belief_expected_collection_weight=1.0,
            belief_information_gain_weight=0.0,
            belief_path_cost_weight=0.0,
            belief_empty_goal_risk_weight=0.0,
            belief_rollout_collection_weight=0.0,
            belief_efficiency_score=False,
        ),
        grid=replace(cfg.grid, nx=30, ny=20),
    )
    grid = make_grid(cfg.world, cfg.grid)
    density_map = init_density_map(grid, cfg.grid, cfg.world)
    density_map.expected_count *= 0.0
    density_map.expected_count[(np.abs(grid.yy - 20.0) <= 1.1) & (np.abs(grid.xx - 29.0) <= 0.1)] = 5.0
    density_map.expected_count[
        (np.abs(grid.yy - 20.0) <= 1.1)
        & (grid.xx >= 31.0)
        & (grid.xx <= 39.0)
    ] = 1.0

    decision = choose_goal(
        0.0,
        np.array(cfg.world.depot, dtype=float),
        initial_state(cfg.world, cfg.planner),
        density_map,
        cfg.world,
        cfg.platform,
        cfg.planner,
        TargetQueue(cfg.planner),
        field=None,
    )

    assert decision.mode == "belief_horizon"
    assert decision.details["candidate_type"] == "density_transect"
    assert decision.point[0] > 34.0
    assert decision.details["score_expected_collection"] > 5.0


def test_belief_horizon_refines_uncertain_radar_target_before_collection() -> None:
    cfg = scenario_config("static_calm", 0, "belief_horizon")
    cfg = replace(
        cfg,
        world=WorldConfig(width_m=60.0, height_m=40.0, depot_x_m=5.0, depot_y_m=20.0, n_debris=1),
        planner=replace(
            cfg.planner,
            belief_candidate_count=5,
            belief_density_peak_count=0,
            belief_entropy_peak_count=0,
            belief_refine_confidence_weight=2.0,
            belief_path_cost_weight=0.0,
        ),
        grid=replace(cfg.grid, nx=30, ny=20),
    )
    grid = make_grid(cfg.world, cfg.grid)
    density_map = init_density_map(grid, cfg.grid, cfg.world)
    target_queue = TargetQueue(cfg.planner)
    det = Detection(
        "radar",
        np.array([40.0, 20.0]),
        0.9,
        source_index=None,
        is_false=False,
        range_m=30.0,
        localization_sigma_m=4.0,
    )
    target_queue.add_detections([det, det], 0.0, cfg.world)

    decision = choose_goal(
        0.0,
        np.array(cfg.world.depot, dtype=float),
        initial_state(cfg.world, cfg.planner),
        density_map,
        cfg.world,
        cfg.platform,
        cfg.planner,
        target_queue,
        field=None,
    )

    assert decision.details["candidate_type"] == "confirmed_target_refine"
    assert 25.0 < decision.point[0] < 40.0
    assert decision.details["target_uncertainty_m"] > cfg.planner.belief_collect_sigma_threshold_m
    assert decision.details["target_track_id"] == 1.0


def test_belief_horizon_confirmed_candidate_logs_track_id() -> None:
    cfg = scenario_config("static_calm", 0, "belief_horizon")
    cfg = replace(
        cfg,
        world=WorldConfig(width_m=60.0, height_m=40.0, depot_x_m=5.0, depot_y_m=20.0, n_debris=1),
        planner=replace(
            cfg.planner,
            belief_candidate_count=5,
            belief_density_peak_count=0,
            belief_entropy_peak_count=0,
            belief_refinement_enabled=False,
        ),
        grid=replace(cfg.grid, nx=30, ny=20),
    )
    grid = make_grid(cfg.world, cfg.grid)
    density_map = init_density_map(grid, cfg.grid, cfg.world)
    target_queue = TargetQueue(cfg.planner)
    det = Detection(
        "camera",
        np.array([35.0, 20.0]),
        0.9,
        source_index=None,
        is_false=False,
        range_m=12.0,
        localization_sigma_m=0.6,
    )
    target_queue.add_detections([det, det], 0.0, cfg.world)

    decision = choose_goal(
        0.0,
        np.array(cfg.world.depot, dtype=float),
        initial_state(cfg.world, cfg.planner),
        density_map,
        cfg.world,
        cfg.platform,
        cfg.planner,
        target_queue,
        field=None,
    )

    assert decision.details["candidate_type"] in {"confirmed_target", "confirmed_target_transect"}
    assert decision.details["target_track_id"] == 1.0


def test_belief_horizon_provisional_uses_single_high_confidence_track() -> None:
    cfg = scenario_config("static_calm", 0, "belief_horizon_provisional")
    cfg = replace(
        cfg,
        world=WorldConfig(width_m=60.0, height_m=40.0, depot_x_m=5.0, depot_y_m=20.0, n_debris=1),
        planner=replace(
            cfg.planner,
            belief_candidate_count=5,
            belief_density_peak_count=0,
            belief_entropy_peak_count=0,
            belief_provisional_min_confidence=0.8,
            belief_provisional_confidence_scale=0.8,
        ),
        grid=replace(cfg.grid, nx=30, ny=20),
    )
    grid = make_grid(cfg.world, cfg.grid)
    density_map = init_density_map(grid, cfg.grid, cfg.world)
    density_map.expected_count *= 0.0
    target_queue = TargetQueue(cfg.planner)
    det = Detection(
        "camera",
        np.array([35.0, 20.0]),
        0.9,
        source_index=None,
        is_false=False,
        range_m=12.0,
        localization_sigma_m=0.6,
    )
    target_queue.add_detections([det], 0.0, cfg.world)

    decision = choose_goal(
        0.0,
        np.array(cfg.world.depot, dtype=float),
        initial_state(cfg.world, cfg.planner),
        density_map,
        cfg.world,
        cfg.platform,
        cfg.planner,
        target_queue,
        field=None,
    )

    assert decision.mode == "belief_horizon"
    assert str(decision.details["candidate_type"]).startswith("provisional_target")
    assert decision.details["score_target_confirmation"] > 0.0


def test_provisional_track_does_not_suppress_density_candidates() -> None:
    cfg = scenario_config("static_calm", 0, "belief_horizon_provisional")
    cfg = replace(
        cfg,
        world=WorldConfig(width_m=60.0, height_m=40.0, depot_x_m=5.0, depot_y_m=20.0, n_debris=1),
        planner=replace(
            cfg.planner,
            belief_candidate_count=12,
            belief_density_peak_count=2,
            belief_transect_count=1,
            belief_entropy_peak_count=0,
            belief_density_signal_threshold=0.0,
            belief_provisional_min_confidence=0.8,
            belief_provisional_confidence_scale=0.8,
        ),
        grid=replace(cfg.grid, nx=30, ny=20),
    )
    grid = make_grid(cfg.world, cfg.grid)
    density_map = init_density_map(grid, cfg.grid, cfg.world)
    density_map.expected_count *= 0.0
    density_map.expected_count[15, 20] = 2.0
    target_queue = TargetQueue(cfg.planner)
    det = Detection(
        "camera",
        np.array([18.0, 20.0]),
        0.9,
        source_index=None,
        is_false=False,
        range_m=8.0,
        localization_sigma_m=0.6,
    )
    target_queue.add_detections([det], 0.0, cfg.world)

    candidates = _belief_candidates(
        np.array(cfg.world.depot, dtype=float),
        initial_state(cfg.world, cfg.planner),
        density_map,
        cfg.world,
        cfg.platform,
        cfg.planner,
        target_queue,
        0.0,
    )
    kinds = {kind for _, kind, *_ in candidates}

    assert "provisional_target" in kinds or "provisional_target_transect" in kinds
    assert "density_peak" in kinds or "density_transect" in kinds


def test_approach_aware_candidate_offsets_use_belief_focus_only() -> None:
    cfg = scenario_config("static_calm", 0, "belief_horizon_approach_aware")
    current = np.array([5.0, 20.0], dtype=float)
    focus = np.array([30.0, 20.0], dtype=float)

    candidates = _approach_aware_candidates(
        current,
        focus,
        "density_peak",
        cfg.world,
        cfg.platform,
        cfg.planner,
        0.0,
        0.0,
        0.0,
    )

    assert candidates
    kinds = {kind for _, kind, *_ in candidates}
    assert kinds == {"density_approach"}
    assert any(abs(float(point[1] - focus[1])) > 0.1 for point, *_ in candidates)


def test_approach_aware_swept_endpoint_can_outscore_point_goal_on_offset_patch() -> None:
    cfg = scenario_config("static_calm", 0, "belief_horizon_approach_aware")
    cfg = replace(
        cfg,
        world=WorldConfig(width_m=60.0, height_m=40.0, depot_x_m=5.0, depot_y_m=20.0, n_debris=1),
        platform=replace(cfg.platform, collection_width_m=1.0, collection_length_m=2.0),
        planner=replace(
            cfg.planner,
            candidate_spacing_m=4.0,
            belief_candidate_count=20,
            belief_density_signal_threshold=0.0,
            belief_density_peak_count=1,
            belief_transect_count=1,
            belief_entropy_peak_count=0,
            belief_approach_offset_count=5,
            belief_approach_offset_step_m=1.0,
            belief_approach_extension_m=2.0,
            belief_approach_switch_margin=-1e9,
            belief_approach_local_support_weight=0.0,
        ),
        grid=replace(cfg.grid, nx=60, ny=40),
    )
    grid = make_grid(cfg.world, cfg.grid)
    density_map = init_density_map(grid, cfg.grid, cfg.world)
    density_map.expected_count *= 0.0
    density_map.expected_count[(np.abs(grid.xx - 30.5) <= 0.6) & (np.abs(grid.yy - 22.5) <= 0.6)] = 3.0
    current = np.array(cfg.world.depot, dtype=float)
    direct = np.array([30.5, 22.5], dtype=float)
    candidates = _belief_candidates(
        current,
        initial_state(cfg.world, cfg.planner),
        density_map,
        cfg.world,
        cfg.platform,
        cfg.planner,
        TargetQueue(cfg.planner),
        0.0,
    )
    approach_scores = [
        _swept_expected_count(density_map, current, point, cfg.platform)
        for point, kind, *_ in candidates
        if kind == "density_approach"
    ]

    assert approach_scores
    assert max(approach_scores) >= _swept_expected_count(density_map, current, direct, cfg.platform)

    decision = choose_goal(
        0.0,
        current,
        initial_state(cfg.world, cfg.planner),
        density_map,
        cfg.world,
        cfg.platform,
        cfg.planner,
        TargetQueue(cfg.planner),
        field=None,
    )

    assert decision.details["candidate_type"] == "density_approach"
    assert decision.details["score_expected_collection"] > 0.0


def test_belief_horizon_builds_local_sweep_for_ready_camera_target() -> None:
    cfg = scenario_config("static_calm", 0, "belief_horizon")
    cfg = replace(
        cfg,
        world=WorldConfig(width_m=60.0, height_m=40.0, depot_x_m=5.0, depot_y_m=20.0, n_debris=1),
        planner=replace(
            cfg.planner,
            belief_candidate_count=5,
            belief_density_peak_count=0,
            belief_entropy_peak_count=0,
            belief_local_sweep_enabled=True,
            belief_local_sweep_lanes=3,
        ),
        grid=replace(cfg.grid, nx=30, ny=20),
    )
    grid = make_grid(cfg.world, cfg.grid)
    density_map = init_density_map(grid, cfg.grid, cfg.world)
    target_queue = TargetQueue(cfg.planner)
    det = Detection(
        "camera",
        np.array([35.0, 20.0]),
        0.9,
        source_index=None,
        is_false=False,
        range_m=12.0,
        localization_sigma_m=0.6,
    )
    target_queue.add_detections([det, det], 0.0, cfg.world)
    state = initial_state(cfg.world, cfg.planner)

    decision = choose_goal(
        0.0,
        np.array(cfg.world.depot, dtype=float),
        state,
        density_map,
        cfg.world,
        cfg.platform,
        cfg.planner,
        target_queue,
        field=None,
    )

    assert decision.mode == "belief_horizon"
    assert decision.reason == "confirmed_target_local_sweep"
    assert decision.details["candidate_type"] == "confirmed_target_local_sweep"
    assert decision.details["local_sweep_lanes"] == 3.0
    assert state.current_route is not None
    assert len(state.current_route) == 3


def test_belief_cluster_route_builds_multi_point_route_from_density_patch() -> None:
    cfg = scenario_config("static_calm", 0, "belief_cluster_route")
    cfg = replace(
        cfg,
        world=WorldConfig(width_m=80.0, height_m=50.0, depot_x_m=5.0, depot_y_m=25.0, n_debris=1),
        platform=replace(cfg.platform, collection_width_m=2.0, collection_length_m=2.0),
        planner=replace(
            cfg.planner,
            candidate_spacing_m=4.0,
            belief_density_peak_count=12,
            belief_cluster_route_candidate_count=12,
            belief_cluster_route_max_points=4,
            belief_cluster_route_radius_m=24.0,
            belief_cluster_route_max_length_m=90.0,
            belief_cluster_route_min_points=2,
            belief_cluster_route_switch_margin=-1e9,
            belief_cluster_route_confirmed_followups_only=False,
            belief_entropy_peak_count=0,
        ),
        grid=replace(cfg.grid, nx=40, ny=25),
    )
    grid = make_grid(cfg.world, cfg.grid)
    density_map = init_density_map(grid, cfg.grid, cfg.world)
    density_map.expected_count *= 0.0
    for center_x in [24.0, 32.0, 40.0]:
        density_map.expected_count[
            (np.abs(grid.yy - 25.0) <= 1.1)
            & (np.abs(grid.xx - center_x) <= 1.1)
        ] = 2.0
    state = initial_state(cfg.world, cfg.planner)

    decision = choose_goal(
        0.0,
        np.array(cfg.world.depot, dtype=float),
        state,
        density_map,
        cfg.world,
        cfg.platform,
        cfg.planner,
        TargetQueue(cfg.planner),
        field=None,
    )

    assert decision.mode == "belief_horizon"
    assert decision.reason == "belief_cluster_route"
    assert decision.details["candidate_type"] == "cluster_route_transect"
    assert decision.details["cluster_route_points"] >= 2.0
    assert state.current_route is not None
    assert len(state.current_route) >= 2


def test_belief_cluster_route_runs_and_logs_route_details() -> None:
    cfg = scenario_config("static_calm", 2, "belief_cluster_route")
    cfg = replace(
        cfg,
        world=WorldConfig(width_m=50.0, height_m=50.0, depot_x_m=5.0, depot_y_m=25.0, n_debris=8),
        platform=replace(cfg.platform, max_path_m=120.0, tmax_s=400.0),
        planner=replace(
            cfg.planner,
            candidate_spacing_m=8.0,
            belief_density_signal_threshold=0.0,
            belief_cluster_route_candidate_count=8,
            belief_cluster_route_max_points=3,
            belief_cluster_route_radius_m=18.0,
            belief_cluster_route_max_length_m=80.0,
            belief_cluster_route_switch_margin=-1e9,
            belief_cluster_route_confirmed_followups_only=False,
        ),
        grid=replace(cfg.grid, nx=25, ny=25),
    )
    result = run_simulation(cfg)
    assert result.summary["mode"] == "belief_cluster_route"
    assert np.isfinite(result.density_map.expected_count).all()
    starts = result.events[result.events["event"] == "goal_started"]
    assert not starts.empty
    assert "cluster_route_points" in starts.columns


def test_belief_orienteering_scores_route_horizon_without_locking_route() -> None:
    cfg = scenario_config("static_calm", 0, "belief_orienteering")
    cfg = replace(
        cfg,
        world=WorldConfig(width_m=80.0, height_m=50.0, depot_x_m=5.0, depot_y_m=25.0, n_debris=1),
        platform=replace(cfg.platform, collection_width_m=2.0, collection_length_m=2.0),
        planner=replace(
            cfg.planner,
            candidate_spacing_m=4.0,
            belief_density_signal_threshold=0.0,
            belief_density_peak_count=10,
            belief_transect_count=4,
            belief_unconfirmed_candidate_max_travel_m=120.0,
            belief_orienteering_candidate_count=10,
            belief_orienteering_depth=3,
            belief_orienteering_beam_width=5,
            belief_orienteering_max_first_leg_m=90.0,
            belief_orienteering_max_route_m=140.0,
            belief_orienteering_switch_margin=-1e9,
        ),
        grid=replace(cfg.grid, nx=40, ny=25),
    )
    grid = make_grid(cfg.world, cfg.grid)
    density_map = init_density_map(grid, cfg.grid, cfg.world)
    density_map.expected_count *= 0.0
    for center_x in [24.0, 32.0, 40.0]:
        density_map.expected_count[
            (np.abs(grid.yy - 25.0) <= 1.1)
            & (np.abs(grid.xx - center_x) <= 1.1)
        ] = 2.0
    state = initial_state(cfg.world, cfg.planner)

    decision = choose_goal(
        0.0,
        np.array(cfg.world.depot, dtype=float),
        state,
        density_map,
        cfg.world,
        cfg.platform,
        cfg.planner,
        TargetQueue(cfg.planner),
        field=None,
    )

    assert decision.mode == "belief_orienteering"
    assert decision.reason == "belief_orienteering_score"
    assert decision.details["planning_mode"] == "receding_orienteering"
    assert decision.details["candidate_type"] == "density_transect"
    assert decision.details["orienteering_route_points"] >= 2.0
    assert decision.point[0] > 40.0
    assert state.current_route is None


def test_belief_transect_goal_uses_collection_speed_before_approach_radius() -> None:
    cfg = scenario_config("static_calm", 0, "belief_orienteering")
    far_goal = np.array([80.0, 25.0], dtype=float)
    pos = np.array([10.0, 25.0], dtype=float)

    speed = _motion_speed(
        cfg,
        "belief_orienteering",
        pos,
        far_goal,
        {
            "candidate_type": "density_transect",
            "score_expected_collection": 2.0,
        },
    )

    assert speed == cfg.platform.collection_speed_mps


def test_belief_orienteering_runs_and_logs_horizon_details() -> None:
    cfg = scenario_config("static_calm", 2, "belief_orienteering")
    cfg = replace(
        cfg,
        world=WorldConfig(width_m=50.0, height_m=50.0, depot_x_m=5.0, depot_y_m=25.0, n_debris=8),
        platform=replace(cfg.platform, max_path_m=120.0, tmax_s=400.0),
        planner=replace(
            cfg.planner,
            candidate_spacing_m=8.0,
            belief_density_signal_threshold=0.0,
            belief_unconfirmed_candidate_max_travel_m=80.0,
            belief_orienteering_candidate_count=8,
            belief_orienteering_depth=2,
            belief_orienteering_beam_width=4,
            belief_orienteering_switch_margin=-1e9,
        ),
        grid=replace(cfg.grid, nx=25, ny=25),
    )
    result = run_simulation(cfg)
    assert result.summary["mode"] == "belief_orienteering"
    assert np.isfinite(result.density_map.expected_count).all()
    starts = result.events[result.events["event"] == "goal_started"]
    assert not starts.empty
    assert "orienteering_route_points" in starts.columns


def test_belief_horizon_runs_and_logs_score_components() -> None:
    cfg = scenario_config("static_calm", 2, "belief_horizon")
    cfg = replace(
        cfg,
        world=WorldConfig(width_m=50.0, height_m=50.0, depot_x_m=5.0, depot_y_m=25.0, n_debris=8),
        platform=replace(cfg.platform, max_path_m=120.0, tmax_s=400.0),
        grid=replace(cfg.grid, nx=25, ny=25),
    )
    result = run_simulation(cfg)
    assert result.summary["mode"] == "belief_horizon"
    assert np.isfinite(result.density_map.expected_count).all()
    starts = result.events[result.events["event"] == "goal_started"]
    assert not starts.empty
    assert "score_total" in starts.columns
    assert "score_rollout_collection" in starts.columns
    assert "score_refine_bonus" in starts.columns
    assert starts["score_total"].notna().any()


def test_belief_retarget_mode_runs_and_reports_retarget_count() -> None:
    cfg = scenario_config("static_calm", 1, "belief_horizon_retarget")
    cfg = replace(
        cfg,
        world=WorldConfig(width_m=55.0, height_m=45.0, depot_x_m=5.0, depot_y_m=22.0, n_debris=10),
        platform=replace(cfg.platform, max_path_m=160.0, tmax_s=500.0),
        planner=replace(
            cfg.planner,
            belief_goal_retarget_interval_s=2.0,
            belief_goal_retarget_min_shift_m=0.25,
            belief_goal_retarget_max_shift_m=12.0,
        ),
        grid=replace(cfg.grid, nx=28, ny=24),
    )

    result = run_simulation(cfg)

    assert result.summary["mode"] == "belief_horizon_retarget"
    assert "goal_retarget_count" in result.summary
    assert result.summary["goal_retarget_count"] >= 0
    if result.summary["goal_retarget_count"] > 0:
        assert "goal_retargeted" in set(result.events["event"])


def test_belief_retarget_locked_mode_runs_and_logs_track_lock_fields() -> None:
    cfg = scenario_config("static_calm", 1, "belief_horizon_retarget_locked")
    cfg = replace(
        cfg,
        world=WorldConfig(width_m=55.0, height_m=45.0, depot_x_m=5.0, depot_y_m=22.0, n_debris=10),
        platform=replace(cfg.platform, max_path_m=160.0, tmax_s=500.0),
        planner=replace(
            cfg.planner,
            belief_goal_retarget_interval_s=2.0,
            belief_goal_retarget_min_shift_m=0.25,
            belief_goal_retarget_max_shift_m=12.0,
        ),
        grid=replace(cfg.grid, nx=28, ny=24),
    )

    result = run_simulation(cfg)

    assert result.summary["mode"] == "belief_horizon_retarget_locked"
    assert "goal_retarget_count" in result.summary
    starts = result.events[result.events["event"] == "goal_started"]
    assert "target_track_id" in starts.columns
    retargeted = result.events[result.events["event"] == "goal_retargeted"]
    if not retargeted.empty:
        assert "old_target_track_id" in retargeted.columns
        assert "target_track_id" in retargeted.columns
        locked = retargeted[retargeted["same_track_required"] == True]  # noqa: E712
        if not locked.empty:
            assert (locked["old_target_track_id"] == locked["target_track_id"]).all()


def test_region_adaptive_retarget_policy_locks_only_drifting_cross_region_target() -> None:
    static_cfg = scenario_config("static_calm", 0, "belief_horizon_retarget_region")
    drift_cfg = scenario_config("weak_drift", 0, "belief_horizon_retarget_region")
    old_goal = np.array([20.0, 20.0], dtype=float)
    near_goal = np.array([21.0, 20.0], dtype=float)
    far_goal = np.array([25.0, 20.0], dtype=float)

    static_policy = _retarget_track_policy(static_cfg, "target", 3, old_goal, far_goal)
    drift_near_policy = _retarget_track_policy(drift_cfg, "target", 3, old_goal, near_goal)
    drift_far_policy = _retarget_track_policy(drift_cfg, "target", 3, old_goal, far_goal)
    density_policy = _retarget_track_policy(drift_cfg, "density", 0, old_goal, far_goal)

    assert static_policy["drift_sensitive"] is False
    assert static_policy["same_track_required"] is False
    assert drift_near_policy["drift_sensitive"] is True
    assert drift_near_policy["same_region"] is True
    assert drift_near_policy["same_track_required"] is False
    assert drift_far_policy["same_region"] is False
    assert drift_far_policy["same_track_required"] is True
    assert density_policy["same_track_required"] is False


def test_drift_switch_retarget_policy_locks_drifting_targets_only() -> None:
    static_cfg = scenario_config("static_calm", 0, "belief_horizon_retarget_drift_switch")
    drift_cfg = scenario_config("weak_drift", 0, "belief_horizon_retarget_drift_switch")
    old_goal = np.array([20.0, 20.0], dtype=float)
    far_goal = np.array([25.0, 20.0], dtype=float)

    static_policy = _retarget_track_policy(static_cfg, "target", 3, old_goal, far_goal)
    drift_policy = _retarget_track_policy(drift_cfg, "target", 3, old_goal, far_goal)
    density_policy = _retarget_track_policy(drift_cfg, "density", 0, old_goal, far_goal)

    assert static_policy["drift_switch"] is True
    assert static_policy["drift_sensitive"] is False
    assert static_policy["same_track_required"] is False
    assert drift_policy["drift_switch"] is True
    assert drift_policy["drift_sensitive"] is True
    assert drift_policy["same_track_required"] is True
    assert density_policy["same_track_required"] is False


def test_belief_retarget_region_mode_runs_and_logs_region_policy_fields() -> None:
    cfg = scenario_config("weak_drift", 1, "belief_horizon_retarget_region")
    cfg = replace(
        cfg,
        world=WorldConfig(width_m=55.0, height_m=45.0, depot_x_m=5.0, depot_y_m=22.0, n_debris=10),
        platform=replace(cfg.platform, max_path_m=160.0, tmax_s=500.0),
        planner=replace(
            cfg.planner,
            belief_goal_retarget_interval_s=2.0,
            belief_goal_retarget_min_shift_m=0.25,
            belief_goal_retarget_max_shift_m=12.0,
        ),
        grid=replace(cfg.grid, nx=28, ny=24),
    )

    result = run_simulation(cfg)

    assert result.summary["mode"] == "belief_horizon_retarget_region"
    assert "goal_retarget_count" in result.summary
    retargeted = result.events[result.events["event"] == "goal_retargeted"]
    if not retargeted.empty:
        assert "region_adaptive" in retargeted.columns
        assert "same_region" in retargeted.columns
        assert "drift_speed_mps" in retargeted.columns
        assert retargeted["region_adaptive"].astype(bool).all()


def test_density_risk_gate_filters_low_efficiency_density_only() -> None:
    cfg = scenario_config("static_calm", 0, "belief_horizon_density_risk_gate")
    planner = cfg.planner

    accepted_low, low_expected_per_m, low_benefit_per_m, low_penalty = _passes_density_risk_gate(
        "density_peak",
        expected_collection=0.10,
        rollout_collection=0.25,
        information_gain=0.02,
        effort_m=60.0,
        planner=planner,
    )
    accepted_high, high_expected_per_m, high_benefit_per_m, high_penalty = _passes_density_risk_gate(
        "density_peak",
        expected_collection=5.0,
        rollout_collection=3.0,
        information_gain=0.10,
        effort_m=40.0,
        planner=planner,
    )
    hard_rejected, _, _, hard_penalty = _passes_density_risk_gate(
        "density_peak",
        expected_collection=0.01,
        rollout_collection=0.01,
        information_gain=0.0,
        effort_m=70.0,
        planner=planner,
    )
    target_accepted, _, _, target_penalty = _passes_density_risk_gate(
        "confirmed_target",
        expected_collection=0.0,
        rollout_collection=0.0,
        information_gain=0.0,
        effort_m=80.0,
        planner=planner,
    )

    assert accepted_low is True
    assert low_expected_per_m < planner.belief_density_gate_min_expected_per_m
    assert low_benefit_per_m < planner.belief_density_gate_min_benefit_per_m
    assert low_penalty > 0.0
    assert accepted_high is True
    assert high_expected_per_m >= planner.belief_density_gate_min_expected_per_m
    assert high_penalty == 0.0
    assert hard_rejected is False
    assert hard_penalty > 0.0
    assert target_accepted is True
    assert target_penalty == 0.0


def test_density_risk_gate_logs_gate_decision_for_density_candidate() -> None:
    cfg = scenario_config("static_calm", 0, "belief_horizon_density_risk_gate")
    cfg = replace(
        cfg,
        world=WorldConfig(width_m=80.0, height_m=50.0, depot_x_m=5.0, depot_y_m=25.0, n_debris=1),
        platform=replace(cfg.platform, collection_width_m=1.0, collection_length_m=1.0),
        planner=replace(
            cfg.planner,
            candidate_spacing_m=8.0,
            belief_density_signal_threshold=0.0,
            belief_entropy_peak_count=0,
            belief_unconfirmed_candidate_max_travel_m=120.0,
        ),
        grid=replace(cfg.grid, nx=40, ny=25),
    )
    grid = make_grid(cfg.world, cfg.grid)
    density_map = init_density_map(grid, cfg.grid, cfg.world)
    density_map.expected_count *= 0.0
    density_map.expected_count[(np.abs(grid.yy - 25.0) <= 1.1) & (np.abs(grid.xx - 24.0) <= 1.1)] = 2.0
    state = initial_state(cfg.world, cfg.planner)

    decision = choose_goal(
        0.0,
        np.array(cfg.world.depot, dtype=float),
        state,
        density_map,
        cfg.world,
        cfg.platform,
        cfg.planner,
        TargetQueue(cfg.planner),
        field=None,
    )

    assert decision.mode == "belief_horizon"
    assert "density_gate_passed" in decision.details or decision.details.get("density_gate_fallback") == 1.0


def test_static_failure_diagnostics_count_local_truth_without_planner_access() -> None:
    field = _field_at([(2.0, 0.0), (4.0, 0.0), (0.0, 5.0), (20.0, 20.0)])
    local_count, local_mass, nearest = _true_local_stats(field, np.array([0.0, 0.0]), 5.1)
    swept_count = _true_swept_count(
        field,
        np.array([0.0, 0.0]),
        np.array([6.0, 0.0]),
        PlatformConfig(collection_width_m=1.0, collection_length_m=1.0),
    )

    assert local_count == 3
    assert local_mass > 0.0
    assert np.isclose(nearest, 2.0)
    assert swept_count == 2


def test_static_failure_diagnostics_are_saved_in_summary_and_events() -> None:
    cfg = scenario_config("static_calm", 0, "belief_horizon")
    cfg = replace(
        cfg,
        world=WorldConfig(width_m=45.0, height_m=45.0, depot_x_m=5.0, depot_y_m=22.0, n_debris=8),
        platform=replace(cfg.platform, max_path_m=120.0, tmax_s=400.0),
        grid=replace(cfg.grid, nx=24, ny=24),
    )

    result = run_simulation(cfg)
    starts = result.events[result.events["event"] == "goal_started"]
    completes = result.events[result.events["event"] == "goal_completed"]

    assert "first_detection_path_m" in result.summary
    assert "first_collection_path_m" in result.summary
    assert "density_empty_goal_rate" in result.summary
    assert "missed_local_opportunity_rate" in result.summary
    assert "true_local_count" in starts.columns
    assert "true_swept_count" in starts.columns
    assert "candidate_group" in starts.columns
    assert "true_local_remaining_count" in completes.columns
    assert "missed_local_opportunity" in completes.columns
