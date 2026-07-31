from __future__ import annotations

from cleanup_sim.confirmatory import build_confirmatory_arms, config_for_arm


def test_confirmatory_arms_include_baseline_and_candidate_hybrid() -> None:
    labels = [arm.label for arm in build_confirmatory_arms()]

    assert labels == ["lawnmower", "active", "detected_tsp", "hybrid_base", "hybrid_candidate_v2"]


def test_candidate_hybrid_changes_only_switch_threshold() -> None:
    base = config_for_arm("clustered_base", 0, build_confirmatory_arms()[3])
    candidate = config_for_arm("clustered_base", 0, build_confirmatory_arms()[4])

    assert base.planner.mode == "hybrid"
    assert candidate.planner.mode == "hybrid"
    assert base.planner.hybrid_explore_entropy_threshold == 0.18
    assert candidate.planner.hybrid_explore_entropy_threshold == 0.24
    assert candidate.planner.target_confirm_hits == base.planner.target_confirm_hits
    assert candidate.planner.detected_confirm_prob == base.planner.detected_confirm_prob
    assert candidate.planner.target_false_suppress_radius_m == base.planner.target_false_suppress_radius_m
