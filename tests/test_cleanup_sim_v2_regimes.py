from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json

import numpy as np
import pandas as pd
import pytest

from cleanup_sim_v2 import simulation
from cleanup_sim_v2.analyze_regimes import analyze_manifest, config_from_dict
from cleanup_sim_v2.config import GridConfig, WorldConfig, scenario_config
from cleanup_sim_v2.io import save_run
from cleanup_sim_v2.mapping import init_density_map, make_grid
from cleanup_sim_v2.regimes import add_oracle_gaps, goal_snapshot, map_concentration, oracle_pair_key, run_metrics
from cleanup_sim_v2.targets import TargetTrack


def small_config():
    cfg = scenario_config("strong_drift", 300, "adaptive_mission")
    return replace(cfg, world=WorldConfig(width_m=10, height_m=10, depot_x_m=5, depot_y_m=5, n_debris=5),
                   grid=GridConfig(nx=10, ny=10),
                   hydro=replace(cfg.hydro, current_x_mps=0.1, current_y_mps=0, windage=0, diffusivity_m2_s=0.25),
                   platform=replace(cfg.platform, collection_width_m=2, collection_speed_mps=0.5, sensor_period_s=2),
                   planner=replace(cfg.planner, target_stale_after_s=20),
                   sensors=replace(cfg.sensors, camera=replace(cfg.sensors.camera, range_m=2), radar=replace(cfg.sensors.radar, range_m=2)))


def test_concentration_uniform_point_mass_scale_invariance_and_missing_mass() -> None:
    assert map_concentration(np.ones((2, 2))) == 0.0
    assert map_concentration(np.array([1, 0, 0, 0])) == 1.0
    assert map_concentration(np.array([1, 2, 3])) == pytest.approx(map_concentration(np.array([10, 20, 30])))
    assert np.isnan(map_concentration(np.zeros(4)))
    with pytest.raises(ValueError):
        map_concentration(np.array([-1, 2]))


def test_goal_snapshot_has_physical_units_filters_fresh_tracks_and_does_not_mutate() -> None:
    cfg = small_config()
    density = init_density_map(make_grid(cfg.world, cfg.grid), cfg.grid, cfg.world)
    tracks = [TargetTrack(np.array(point, dtype=float), 1.0, 10, 0, last_seen,
                          localization_sigma_m=0.5, sensors={"camera", "radar"})
              for point, last_seen in [([5, 5], 80), ([5, 5], 79), ([9, 9], 99)]]
    tracks[0].source_ids = {123456}  # Truth labels must have no influence.
    route = [np.array([8., 9.]), np.array([8., 5.])]
    before = deepcopy(tracks)
    snapshot = goal_snapshot(cfg, 100, np.array([5., 5.]), route[0], density, tracks, route, 0)
    assert snapshot["regime_response_time_nominal_s"] == 12
    assert snapshot["regime_drift_response_width"] == pytest.approx(0.6)
    assert snapshot["regime_diffusion_response_width"] == pytest.approx(np.sqrt(12) / 2)
    assert snapshot["regime_fresh_target_count"] == 1
    assert snapshot["regime_reachable_area_m2"] == 12
    assert snapshot["regime_fresh_target_density_per_m2"] == 1 / 12
    assert snapshot["regime_fresh_target_sigma_width_median"] == 0.25
    assert snapshot["regime_queued_route_length_m"] == 9
    assert snapshot["regime_queued_route_time_nominal_s"] == 26
    assert snapshot["regime_route_staleness_ratio"] == 1.3
    assert snapshot["regime_route_drift_width"] == 1.3
    for original, after in zip(before, tracks):
        assert np.array_equal(original.position, after.position)
        assert original.last_seen_s == after.last_seen_s
    tracks[0].source_ids.clear()
    assert goal_snapshot(cfg, 100, np.array([5., 5.]), route[0], density, tracks, route, 0) == snapshot


def test_snapshot_no_route_zero_drift_and_exhausted_path_have_defined_missingness() -> None:
    cfg = small_config()
    cfg = replace(cfg, hydro=replace(cfg.hydro, current_x_mps=0, diffusivity_m2_s=0))
    density = init_density_map(make_grid(cfg.world, cfg.grid), cfg.grid, cfg.world)
    snap = goal_snapshot(cfg, 0, np.array([5., 5.]), np.array([5., 5.]), density, [], None, cfg.platform.max_path_m)
    assert snap["regime_drift_response_width"] == 0
    assert snap["regime_diffusion_response_width"] == 0
    assert snap["regime_route_staleness_ratio"] == 0
    assert snap["regime_fresh_target_count"] == 0
    assert np.isnan(snap["regime_fresh_target_density_per_m2"])
    assert np.isnan(snap["regime_fresh_target_sigma_width_median"])


def test_reachable_area_is_clipped_by_grid_world_boundary() -> None:
    cfg = small_config()
    density = init_density_map(make_grid(cfg.world, cfg.grid), cfg.grid, cfg.world)
    snap = goal_snapshot(cfg, 0, np.array([0., 5.]), np.array([2., 5.]), density, [], None, 0)
    assert snap["regime_reachable_area_m2"] == 6.0


def test_actual_leg_drift_uses_duration_and_excludes_returns_and_unfinished_legs() -> None:
    cfg = small_config()
    summary = dict(path_length_m=1000, empty_goal_arrivals=0, evaluated_goal_count=2,
                   wasted_path_to_empty_goals=0, false_detection_count=0, true_detection_count=1)
    events = pd.DataFrame([
        dict(event="goal_completed", mode="route", goal_time_s=20),
        dict(event="goal_completed", mode="belief_horizon", goal_time_s=40),
        dict(event="goal_completed", mode="return", goal_time_s=1000),
        dict(event="goal_started", mode="route", goal_time_s=999),
    ])
    metrics = run_metrics(cfg, summary, events)
    assert metrics["regime_outcome_completed_leg_n"] == 2
    assert metrics["regime_outcome_mean_completed_leg_time_s"] == 30
    assert metrics["regime_outcome_mean_completed_leg_drift_width"] == 1.5


def test_old_or_partial_events_do_not_invent_snapshot_metrics() -> None:
    cfg = small_config()
    summary = dict(path_length_m=1000, empty_goal_arrivals=2, evaluated_goal_count=4,
                   wasted_path_to_empty_goals=250, false_detection_count=3, true_detection_count=6)
    events = pd.DataFrame([{"event": "goal_started"}, {"event": "goal_started", "regime_snapshot_version": 1,
                                                               "regime_map_concentration": 0.5},
                           {"event": "goal_completed", "regime_snapshot_version": 1, "regime_map_concentration": 1.0}])
    metrics = run_metrics(cfg, summary, events)
    assert metrics["regime_goal_snapshot_coverage"] == 0.5
    assert metrics["regime_goal_start_mean_map_concentration"] == 0.5
    assert metrics["regime_goal_start_valid_n_map_concentration"] == 1
    assert np.isnan(metrics["regime_goal_start_mean_route_drift_width"])
    assert metrics["regime_outcome_empty_visit_fraction"] == 0.5
    assert metrics["regime_outcome_wasted_path_fraction"] == 0.25
    assert metrics["regime_outcome_false_marks_per_km"] == 3
    assert metrics["regime_outcome_false_to_true_marks"] == 0.5
    assert metrics["regime_config_expected_clutter_per_s"] == pytest.approx(
        (metrics["regime_config_expected_camera_clutter_per_scan"] + metrics["regime_config_expected_radar_clutter_per_scan"]) / 2)
    summary.update(path_length_m=0, evaluated_goal_count=0, true_detection_count=0)
    missing = run_metrics(cfg, summary, events.iloc[:1])
    assert np.isnan(missing["regime_outcome_empty_visit_fraction"])
    assert np.isnan(missing["regime_outcome_false_to_true_marks"])
    assert missing["regime_goal_snapshot_count"] == 0


def test_oracle_pairing_requires_same_physics_seed_and_clean_execution_identity() -> None:
    cfg = small_config().to_dict()
    provenance = dict(git_dirty=False, git_commit_full="a" * 40, source_sha256="source", environment_sha256="env")
    key = oracle_pair_key(cfg, provenance)
    oracle = deepcopy(cfg)
    oracle["planner"]["mode"] = "oracle_current_physics"
    assert oracle_pair_key(oracle, provenance) == key
    oracle["platform"]["collection_width_m"] += 1
    assert oracle_pair_key(oracle, provenance) != key
    assert oracle_pair_key(cfg, {**provenance, "environment_sha256": "other"}) != key
    assert oracle_pair_key(cfg, {**provenance, "git_dirty": True}) is None
    rows = [dict(mode="adaptive_mission", oracle_pair_key=key, auc_collected_by_path=0.8, collected_ratio=0.9),
            dict(mode="oracle_current_physics", oracle_pair_key=key, auc_collected_by_path=0.7, collected_ratio=1.0)]
    paired = add_oracle_gaps(rows)
    assert paired[0]["regime_oracle_gap_auc"] == pytest.approx(-0.1)  # Heuristic can lose.
    assert paired[0]["regime_oracle_gap_collected_ratio"] == pytest.approx(0.1)
    assert np.isnan(add_oracle_gaps(rows[:1])[0]["regime_oracle_gap_auc"])
    with pytest.raises(ValueError, match="Duplicate"):
        add_oracle_gaps([*rows, rows[1]])


def test_snapshot_instrumentation_preserves_simulation_and_roundtrips_analysis(tmp_path, monkeypatch) -> None:
    cfg = scenario_config("strong_drift", 300, "adaptive_mission")
    cfg = replace(cfg, platform=replace(cfg.platform, max_path_m=50, tmax_s=100))
    assert config_from_dict(cfg.to_dict()).to_dict() == cfg.to_dict()
    instrumented = simulation.run_simulation(cfg)
    with monkeypatch.context() as patch:
        patch.setattr(simulation, "goal_snapshot", lambda *args: {})
        plain = simulation.run_simulation(cfg)
    assert instrumented.summary == plain.summary
    pd.testing.assert_frame_equal(instrumented.series, plain.series, check_exact=True)
    pd.testing.assert_frame_equal(instrumented.events.drop(columns=[c for c in instrumented.events if c.startswith("regime_")]),
                                  plain.events, check_exact=True)
    np.testing.assert_array_equal(instrumented.field.positions, plain.field.positions)
    np.testing.assert_array_equal(instrumented.density_map.expected_count, plain.density_map.expected_count)
    paths = save_run(instrumented, tmp_path, "probe")
    row = analyze_manifest(paths["manifest"])
    assert row["regime_goal_snapshot_coverage"] == 1
    assert row["regime_goal_start_count"] > 0
    summary = json.loads(paths["summary"].read_text())
    summary["collected"] += 1
    paths["summary"].write_text(json.dumps(summary))
    with pytest.raises(ValueError, match="corrupted summary"):
        analyze_manifest(paths["manifest"])
