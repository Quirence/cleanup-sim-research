from __future__ import annotations

import numpy as np

from cleanup_sim.metrics import TimeSeries, auc_collected_ratio, summarize_run, value_at_budget


def test_value_at_budget_returns_last_known_value_before_budget() -> None:
    assert value_at_budget([0.0, 10.0, 20.0], [0.0, 0.2, 0.5], 15.0) == 0.2
    assert value_at_budget([0.0, 10.0, 20.0], [0.0, 0.2, 0.5], 25.0) == 0.5


def test_auc_collected_ratio_normalizes_by_budget() -> None:
    auc = auc_collected_ratio([0.0, 10.0], [0.0, 1.0], budget=10.0)
    assert 0.49 <= auc <= 0.51


def test_summarize_run_uses_common_path_budget_for_auc() -> None:
    series = TimeSeries(
        time_s=[0.0, 1.0],
        path_m=[0.0, 10.0],
        collected=[0, 10],
        false_visits=[0, 0],
        planner_mode=["active", "active"],
    )

    summary = summarize_run(
        scenario="clustered_base",
        mode="active",
        seed=0,
        total_debris=10,
        collected_count=10,
        collected_mass_kg=1.0,
        total_mass_kg=1.0,
        path_m=10.0,
        path_budget_m=20.0,
        sim_time_s=1.0,
        unload_events=0,
        false_visits=0,
        stop_reason="done",
        target_confirmed=0,
        target_route_attempts=0,
        target_visit_successes=0,
        target_visit_false=0,
        series=series,
        belief=np.array([[0.1]]),
        true_occ=np.array([[False]]),
    )

    assert 0.74 <= summary["auc_collected_by_path"] <= 0.76


def test_summarize_run_separates_initial_and_residual_map_quality() -> None:
    series = TimeSeries(
        time_s=[0.0],
        path_m=[0.0],
        collected=[1],
        false_visits=[0],
        planner_mode=["greedy"],
    )

    summary = summarize_run(
        scenario="clustered_base",
        mode="greedy",
        seed=0,
        total_debris=1,
        collected_count=1,
        collected_mass_kg=1.0,
        total_mass_kg=1.0,
        path_m=0.0,
        path_budget_m=1.0,
        sim_time_s=0.0,
        unload_events=0,
        false_visits=0,
        stop_reason="done",
        target_confirmed=0,
        target_route_attempts=0,
        target_visit_successes=0,
        target_visit_false=0,
        series=series,
        belief=np.array([[0.1]]),
        true_occ=np.array([[True]]),
        residual_true_occ=np.array([[False]]),
    )

    assert summary["initial_brier_score"] > summary["residual_brier_score"]
    assert summary["brier_score"] == summary["residual_brier_score"]
