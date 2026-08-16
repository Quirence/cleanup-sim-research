from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from cleanup_sim_v2 import run_experiments, run_once


def _small_budget_args(*extra: str) -> list[str]:
    return ["--max-path-m", "50", "--tmax-s", "60", *extra]


def test_run_once_main_writes_a_summary_with_reproducibility_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_once",
            "--scenario",
            "static_calm",
            "--mode",
            "greedy",
            "--seed",
            "0",
            "--out-dir",
            str(tmp_path),
            *_small_budget_args(),
        ],
    )

    run_once.main()

    summary_path = tmp_path / "static_calm__greedy__nominal__seed0_summary.json"
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["runner"] == "run_once"
    assert summary["git_commit"] != "unknown"
    assert isinstance(summary["git_dirty"], bool)
    assert "config_hash" in summary


def test_run_experiments_main_writes_summary_aggregate_and_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_experiments",
            "--seeds",
            "2",
            "--seed-start",
            "5",
            "--scenarios",
            "static_calm",
            "--modes",
            "greedy",
            "lawnmower_survey",
            "--out-dir",
            str(tmp_path),
            *_small_budget_args(),
        ],
    )

    run_experiments.main()

    summary_path = tmp_path / "summary.csv"
    aggregate_path = tmp_path / "aggregate_mean_std.csv"
    manifest_path = tmp_path / "run_manifest.json"
    assert summary_path.exists()
    assert aggregate_path.exists()
    assert manifest_path.exists()

    summary_df = pd.read_csv(summary_path)
    # 2 modes x 1 scenario x 2 seeds = 4 rows.
    assert len(summary_df) == 4
    assert set(summary_df["mode"]) == {"greedy", "lawnmower_survey"}
    assert set(summary_df["seed"]) == {5, 6}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["runner"] == "cleanup_sim_v2.run_experiments"
    assert manifest["seeds"] == 2
    assert manifest["seed_start"] == 5
    assert manifest["scenarios"] == ["static_calm"]
    assert manifest["git_commit"] != "unknown"


def test_run_experiments_writes_paired_comparisons_for_adaptive_mission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_experiments",
            "--seeds",
            "1",
            "--scenarios",
            "static_calm",
            "--modes",
            "greedy",
            "adaptive_mission",
            "--out-dir",
            str(tmp_path),
            *_small_budget_args(),
        ],
    )

    run_experiments.main()

    comparisons_path = tmp_path / "paired_comparisons.csv"
    assert comparisons_path.exists()
    comparisons = pd.read_csv(comparisons_path)
    assert set(comparisons["mode_a"]) == {"adaptive_mission"}
    assert "auc_collected_by_path" in set(comparisons["metric"])


def test_run_experiments_checkpoint_writes_partial_files_during_the_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_experiments",
            "--seeds",
            "2",
            "--scenarios",
            "static_calm",
            "--modes",
            "greedy",
            "--checkpoint",
            "--out-dir",
            str(tmp_path),
            *_small_budget_args(),
        ],
    )

    run_experiments.main()

    assert (tmp_path / "summary_partial.csv").exists()
    assert (tmp_path / "aggregate_partial_mean_std.csv").exists()
    partial_df = pd.read_csv(tmp_path / "summary_partial.csv")
    assert len(partial_df) == 2


def test_run_experiments_resume_skips_runs_already_in_the_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    base_args = [
        "run_experiments",
        "--seeds",
        "1",
        "--scenarios",
        "static_calm",
        "--modes",
        "greedy",
        "--checkpoint",
        "--out-dir",
        str(tmp_path),
        *_small_budget_args(),
    ]

    monkeypatch.setattr(sys, "argv", base_args)
    run_experiments.main()
    first_summary = pd.read_csv(tmp_path / "summary.csv")
    assert len(first_summary) == 1

    monkeypatch.setattr(sys, "argv", [*base_args, "--resume"])
    run_experiments.main()

    captured = capsys.readouterr()
    assert "reason=resume" in captured.out
    # The resumed run must not duplicate the already-completed (scenario, mode, seed).
    second_summary = pd.read_csv(tmp_path / "summary.csv")
    assert len(second_summary) == 1
