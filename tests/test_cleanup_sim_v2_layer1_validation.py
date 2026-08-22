from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

from cleanup_sim_v2 import merge_layer1
from cleanup_sim_v2.layer1_validation import ExpectedMatrix, has_failing_issues, validate_summary


def _row(
    *,
    budget: float = 1200.0,
    scenario: str = "static_calm",
    mode: str = "greedy",
    seed: int = 30,
    collected: int = 10,
    collected_ratio: float = 0.1,
    auc: float = 0.05,
    stop_reason: str = "path_budget",
) -> dict:
    return {
        "path_budget_m": budget,
        "scenario": scenario,
        "profile": "nominal",
        "mode": mode,
        "seed": seed,
        "stop_reason": stop_reason,
        "collected": collected,
        "collected_ratio": collected_ratio,
        "auc_collected_by_path": auc,
        "path_length_m": budget + (0.1 if stop_reason == "path_budget" else 0.0),
        "sim_time_s": 100.0,
        "successful_captures": collected,
        "capture_contacts": collected,
        "empty_goal_arrivals": 0,
        "wasted_path_ratio": 0.0,
        "goal_success_rate": 1.0,
        "detection_precision": 1.0,
        "detection_recall": 1.0,
        "collection_precision": 1.0,
        "git_commit": "abc123",
        "git_dirty": False,
    }


def test_validate_summary_detects_missing_expected_runs() -> None:
    df = pd.DataFrame([_row(mode="greedy")])
    expected = ExpectedMatrix(
        budgets=(1200.0,),
        scenarios=("static_calm",),
        modes=("greedy", "oracle_current_physics"),
        profile="nominal",
        seed_start=30,
        seeds=1,
    )

    issues = validate_summary(df, expected=expected)

    assert any(issue.check == "missing_expected_runs" for issue in issues)
    assert has_failing_issues(issues, "major")


def test_validate_summary_accepts_complete_basic_matrix() -> None:
    df = pd.DataFrame(
        [
            _row(mode="greedy", collected=10, collected_ratio=0.1, auc=0.05),
            _row(mode="oracle_current_physics", collected=150, collected_ratio=1.0, auc=0.5, stop_reason="done"),
        ]
    )
    expected = ExpectedMatrix(
        budgets=(1200.0,),
        scenarios=("static_calm",),
        modes=("greedy", "oracle_current_physics"),
        profile="nominal",
        seed_start=30,
        seeds=1,
    )

    issues = validate_summary(df, expected=expected)

    assert not has_failing_issues(issues, "major")


def test_validate_summary_flags_negative_regret_semantics() -> None:
    row = _row(mode="adaptive_mission")
    row["regret_to_best_fixed_auc"] = -0.1
    row["regret_to_best_fixed_collected_ratio"] = 0.0
    df = pd.DataFrame([row])

    issues = validate_summary(df)

    assert any(issue.check == "regret_to_best_fixed_auc_negative" for issue in issues)
    assert has_failing_issues(issues, "major")


def test_merge_layer1_combines_chunks_and_writes_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chunk_a = tmp_path / "chunk_a"
    chunk_b = tmp_path / "chunk_b"
    chunk_a.mkdir()
    chunk_b.mkdir()
    pd.DataFrame(
        [
            _row(mode="greedy", seed=30, collected=10, collected_ratio=0.1, auc=0.05),
            _row(mode="oracle_current_physics", seed=30, collected=150, collected_ratio=1.0, auc=0.5, stop_reason="done"),
        ]
    ).to_csv(chunk_a / "summary.csv", index=False)
    pd.DataFrame(
        [
            _row(mode="greedy", seed=31, collected=12, collected_ratio=0.12, auc=0.06),
            _row(mode="oracle_current_physics", seed=31, collected=150, collected_ratio=1.0, auc=0.5, stop_reason="done"),
        ]
    ).to_csv(chunk_b / "summary.csv", index=False)
    out_dir = tmp_path / "merged"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "merge_layer1",
            str(chunk_a),
            str(chunk_b),
            "--out-dir",
            str(out_dir),
            "--budgets",
            "1200",
            "--scenarios",
            "static_calm",
            "--modes",
            "greedy",
            "oracle_current_physics",
            "--seed-start",
            "30",
            "--seeds",
            "2",
        ],
    )

    merge_layer1.main()

    merged = pd.read_csv(out_dir / "summary_enriched.csv")
    assert len(merged) == 4
    assert (out_dir / "validation_issues.csv").exists()
    assert (out_dir / "merge_manifest.json").exists()
