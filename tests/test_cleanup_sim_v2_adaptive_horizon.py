from __future__ import annotations

import numpy as np
import pandas as pd

from cleanup_sim_v2.adaptive_horizon import (
    EFFECT_METRICS,
    analyze_horizon_results,
    summarize_horizon_events,
)
from cleanup_sim_v2.config import scenario_config
from cleanup_sim_v2.planners import initial_state, pop_route_goal_if_arrived
from cleanup_sim_v2.targets import TargetQueue


def _route_state(*, adaptive: bool):
    cfg = scenario_config("static_calm", 0, "adaptive_mission")
    state = initial_state(cfg.world, cfg.planner)
    state.current_route = [np.array([10.0, 10.0]), np.array([20.0, 20.0])]
    state.current_route_mode = "route"
    state.current_route_details = {"adaptive_selected_policy": "confirmed_route"} if adaptive else {}
    return cfg, state, TargetQueue(cfg.planner)


def test_per_leg_replan_discards_only_remaining_adaptive_route() -> None:
    cfg, committed, targets = _route_state(adaptive=True)
    discarded = pop_route_goal_if_arrived(
        committed,
        np.array([10.0, 10.0]),
        cfg.platform.arrival_tolerance_m,
        targets,
    )
    assert discarded == 0
    assert committed.current_route is not None
    assert len(committed.current_route) == 1

    cfg, replanned, targets = _route_state(adaptive=True)
    discarded = pop_route_goal_if_arrived(
        replanned,
        np.array([10.0, 10.0]),
        cfg.platform.arrival_tolerance_m,
        targets,
        adaptive_replan_after_each_leg=True,
    )
    assert discarded == 1
    assert replanned.current_route is None
    assert replanned.current_route_details == {}

    cfg, nonadaptive, targets = _route_state(adaptive=False)
    discarded = pop_route_goal_if_arrived(
        nonadaptive,
        np.array([10.0, 10.0]),
        cfg.platform.arrival_tolerance_m,
        targets,
        adaptive_replan_after_each_leg=True,
    )
    assert discarded == 0
    assert nonadaptive.current_route is not None


def _analysis_frame(*, scenario_loss: bool = False) -> pd.DataFrame:
    rows = []
    for scenario in ("static_calm", "strong_drift"):
        for seed in (400, 401, 402):
            queue = 0.50
            replan = 0.52
            if scenario_loss and scenario == "strong_drift":
                replan = 0.48
            for variant, collected_ratio in (("queue_commit", queue), ("replan_each_leg", replan)):
                row = {
                    "scenario": scenario,
                    "seed": seed,
                    "horizon_variant": variant,
                    "initial_debris_count": 150,
                    "collected_ratio": collected_ratio,
                    "remaining_count": 150 * (1.0 - collected_ratio),
                    "complete_cleanup": 0,
                }
                row.update({metric: 0.0 for metric in EFFECT_METRICS if metric not in row})
                rows.append(row)
    return pd.DataFrame(rows)


def test_horizon_analysis_uses_seed_blocks_and_declared_primary_rule() -> None:
    effects, report = analyze_horizon_results(_analysis_frame())
    overall = effects[
        (effects["scope"] == "equal_weight_over_scenarios")
        & (effects["metric"] == "collected_ratio")
    ].iloc[0]

    assert overall["paired_runs"] == 3
    assert np.isclose(overall["mean_difference_replan_minus_queue"], 0.02)
    assert report["decision"] == "replan_each_leg"

    _, mixed_report = analyze_horizon_results(_analysis_frame(scenario_loss=True))
    assert mixed_report["decision"] == "ambiguous"


def test_horizon_event_summary_measures_committed_route_exposure() -> None:
    events = pd.DataFrame([
        {
            "event": "goal_started",
            "adaptive_selector_invoked": 1,
            "adaptive_route_continuation": 0,
            "regime_queued_route_points": 0,
            "regime_route_staleness_ratio": 0.0,
        },
        {
            "event": "goal_started",
            "adaptive_selector_invoked": 0,
            "adaptive_route_continuation": 1,
            "regime_queued_route_points": 2,
            "regime_route_staleness_ratio": 0.5,
        },
        {
            "event": "goal_started",
            "adaptive_selector_invoked": 0,
            "adaptive_route_continuation": 1,
            "regime_queued_route_points": 1,
            "regime_route_staleness_ratio": 1.5,
        },
        {"event": "goal_completed", "adaptive_queue_discarded_points": 3},
    ])

    metrics = summarize_horizon_events(events)

    assert metrics["selector_invocations"] == 1
    assert metrics["route_continuations"] == 2
    assert metrics["queue_discarded_points"] == 3
    assert metrics["regime_route_snapshot_coverage"] == 1.0
    assert np.isclose(metrics["queued_route_assignment_fraction"], 2 / 3)
    assert np.isclose(metrics["route_staleness_ratio_mean"], 2 / 3)
    assert np.isclose(metrics["route_staleness_ratio_exceedance_fraction"], 1 / 3)
    assert metrics["queued_route_staleness_ratio_mean"] == 1.0
