from __future__ import annotations

import math

import pandas as pd
import pytest

from cleanup_sim_v2.config import scenario_config
from cleanup_sim_v2.layer1 import (
    enrich_summary,
    evaluate_budget_calibration,
    layer1_config,
    regime_metrics_for_config,
    safety_tmax_s,
    select_nominal_budget,
)


def test_layer1_safety_tmax_uses_protocol_values_for_standard_budgets() -> None:
    assert safety_tmax_s(1200) == 8000
    assert safety_tmax_s(2400) == 13200
    assert safety_tmax_s(3600) == 20000
    assert safety_tmax_s(7200) == 40000


def test_layer1_safety_tmax_uses_formula_for_custom_budget() -> None:
    assert safety_tmax_s(3000) == math.ceil(3.3 * 3000 / 0.6)


def test_layer1_regime_metrics_are_interpretable_for_nominal_config() -> None:
    cfg = layer1_config("static_calm", 0, "belief_horizon", 3600)
    metrics = regime_metrics_for_config(cfg)

    assert metrics["path_budget_m"] == 3600
    assert metrics["safety_tmax_s"] == 20000
    assert metrics["collection_coverage_ratio"] == 0.09
    assert metrics["drift_speed_mps"] == 0.0
    assert metrics["camera_capture_uncertainty_ratio"] > 1.0
    assert metrics["radar_capture_uncertainty_ratio"] > metrics["camera_capture_uncertainty_ratio"]
    assert 0.0 < metrics["expected_camera_clutter_per_scan"] < metrics["expected_radar_clutter_per_scan"]


def test_layer1_config_preserves_scenario_profile_and_sets_budget() -> None:
    cfg = layer1_config("weak_drift", 12, "greedy", 2400)
    base = scenario_config("weak_drift", 12, "greedy")

    assert cfg.seed == base.seed
    assert cfg.scenario == base.scenario
    assert cfg.planner.mode == base.planner.mode
    assert cfg.platform.max_path_m == 2400
    assert cfg.platform.tmax_s == 13200


def test_lawnmower_collect_sweeps_near_domain_edges() -> None:
    cfg = layer1_config("strong_drift", 12, "lawnmower_collect", 7200)

    assert cfg.planner.coverage_spacing_m == pytest.approx(0.8 * cfg.platform.collection_width_m)
    assert cfg.planner.coverage_margin_m == pytest.approx(0.5 * cfg.platform.collection_width_m)


def _fake_budget_rows(path_budget_m: float, oracle_collected: float, best_collected: float) -> list[dict]:
    rows: list[dict] = []
    scenarios = ["static_calm", "weak_drift", "strong_drift", "robot_disturbed"]
    mode_values = {
        "belief_horizon": (best_collected, 0.60),
        "greedy": (max(0.0, best_collected - 0.20), 0.48),
        "confirmed_route": (max(0.0, best_collected - 0.30), 0.40),
        "oracle_current_physics": (oracle_collected, 0.90),
    }
    for scenario in scenarios:
        for mode, (collected, auc) in mode_values.items():
            rows.append(
                {
                    "path_budget_m": path_budget_m,
                    "scenario": scenario,
                    "profile": "nominal",
                    "seed": 30,
                    "mode": mode,
                    "stop_reason": "path_budget" if mode != "oracle_current_physics" else "done",
                    "collected_ratio": collected,
                    "auc_collected_by_path": auc,
                }
            )
    return rows


def test_layer1_budget_gate_selects_minimum_passing_budget() -> None:
    df = pd.DataFrame(
        [
            *_fake_budget_rows(1200, oracle_collected=0.80, best_collected=0.55),
            *_fake_budget_rows(2400, oracle_collected=0.95, best_collected=0.70),
            *_fake_budget_rows(3600, oracle_collected=0.98, best_collected=0.80),
        ]
    )

    calibration = evaluate_budget_calibration(df)

    assert bool(calibration.loc[calibration["path_budget_m"] == 1200, "passes_layer1_budget_gate"].item()) is False
    assert bool(calibration.loc[calibration["path_budget_m"] == 2400, "passes_layer1_budget_gate"].item()) is True
    assert select_nominal_budget(calibration) == 2400


def test_layer1_enrich_summary_adds_regret_against_best_fixed_mode() -> None:
    df = pd.DataFrame(
        [
            {
                "path_budget_m": 2400,
                "scenario": "static_calm",
                "profile": "nominal",
                "seed": 30,
                "mode": "belief_horizon",
                "collected_ratio": 0.5,
                "auc_collected_by_path": 0.4,
            },
            {
                "path_budget_m": 2400,
                "scenario": "static_calm",
                "profile": "nominal",
                "seed": 30,
                "mode": "greedy",
                "collected_ratio": 0.3,
                "auc_collected_by_path": 0.2,
            },
            {
                "path_budget_m": 2400,
                "scenario": "static_calm",
                "profile": "nominal",
                "seed": 30,
                "mode": "adaptive_mission",
                "collected_ratio": 0.45,
                "auc_collected_by_path": 0.35,
            },
        ]
    )

    enriched = enrich_summary(df)
    adaptive = enriched[enriched["mode"] == "adaptive_mission"].iloc[0]

    assert adaptive["best_fixed_auc_collected_by_path"] == 0.4
    assert adaptive["best_fixed_collected_ratio"] == 0.5
    assert adaptive["regret_to_best_fixed_auc"] == pytest.approx(0.05)
    assert adaptive["regret_to_best_fixed_collected_ratio"] == pytest.approx(0.05)
