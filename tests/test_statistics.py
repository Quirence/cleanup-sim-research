from __future__ import annotations

import pandas as pd

from cleanup_sim.statistics import bootstrap_ci, holm_adjust, paired_comparison_table, paired_differences


def test_paired_differences_aligns_by_seed() -> None:
    df = pd.DataFrame({
        "scenario": ["s", "s", "s", "s"],
        "mode": ["a", "b", "a", "b"],
        "seed": [0, 0, 1, 1],
        "collected_ratio": [0.5, 0.7, 0.6, 0.8],
    })
    diffs = paired_differences(df, scenario="s", mode_a="b", mode_b="a", metric="collected_ratio")
    assert diffs == [0.2, 0.2]


def test_holm_adjust_keeps_values_in_probability_range() -> None:
    adjusted = holm_adjust([0.01, 0.04, 0.03])
    assert len(adjusted) == 3
    assert all(0.0 <= p <= 1.0 for p in adjusted)


def test_bootstrap_ci_contains_mean_for_constant_values() -> None:
    low, high = bootstrap_ci([0.5, 0.5, 0.5], seed=0)
    assert low == 0.5
    assert high == 0.5


def test_paired_comparison_table_uses_all_non_reference_modes_by_default() -> None:
    df = pd.DataFrame({
        "scenario": ["s"] * 6,
        "mode": ["hybrid", "active", "active_entropy", "hybrid", "active", "active_entropy"],
        "seed": [0, 0, 0, 1, 1, 1],
        "collected_ratio": [0.8, 0.6, 0.5, 0.9, 0.7, 0.6],
    })

    table = paired_comparison_table(df, metrics=("collected_ratio",))

    assert set(table["mode_b"]) == {"active", "active_entropy"}
