from __future__ import annotations

from cleanup_sim.config import PlannerConfig, scenario_config
from cleanup_sim.confirmatory import FINAL_HYBRID_EXPLORE_ENTROPY_THRESHOLD
from cleanup_sim.sensitivity import apply_sensitivity_case, iter_sensitivity_cases


def test_iter_sensitivity_cases_uses_one_factor_design() -> None:
    cases = iter_sensitivity_cases(PlannerConfig())
    names = [case.name for case in cases]

    assert names[0] == "baseline"
    assert len(cases) == 14
    assert "target_confirm_hits=1" in names
    assert "target_confirm_hits=3" in names
    assert "detected_confirm_prob=0.65" in names
    assert "detected_confirm_prob=0.8" in names
    assert "target_false_suppress_radius_m=8.0" in names
    assert "target_false_suppress_radius_m=16.0" in names
    assert "hybrid_explore_entropy_threshold=0.12" in names
    assert "hybrid_explore_entropy_threshold=0.18" in names
    assert "collect_radius_m=2.5" in names
    assert "bin_capacity_kg=10.0" in names
    assert "bin_capacity_kg=60.0" in names
    assert "speed_mps=1.0" in names
    assert "speed_mps=1.5" in names


def test_apply_sensitivity_case_changes_only_requested_parameter() -> None:
    cfg = scenario_config("clustered_base", 0, "hybrid")
    case = next(case for case in iter_sensitivity_cases(cfg.planner) if case.name == "detected_confirm_prob=0.8")

    updated = apply_sensitivity_case(cfg, case)

    assert updated.planner.detected_confirm_prob == 0.8
    assert updated.planner.target_confirm_hits == cfg.planner.target_confirm_hits
    assert updated.planner.target_false_suppress_radius_m == cfg.planner.target_false_suppress_radius_m
    assert updated.planner.hybrid_explore_entropy_threshold == FINAL_HYBRID_EXPLORE_ENTROPY_THRESHOLD
    assert updated.planner.mode == "hybrid"


def test_apply_sensitivity_case_can_change_robot_parameter() -> None:
    cfg = scenario_config("clustered_base", 0, "hybrid")
    case = next(case for case in iter_sensitivity_cases(cfg.planner) if case.name == "speed_mps=1.0")

    updated = apply_sensitivity_case(cfg, case)

    assert updated.robot.speed_mps == 1.0
    assert updated.robot.collect_radius_m == cfg.robot.collect_radius_m
    assert updated.planner.hybrid_explore_entropy_threshold == FINAL_HYBRID_EXPLORE_ENTROPY_THRESHOLD
