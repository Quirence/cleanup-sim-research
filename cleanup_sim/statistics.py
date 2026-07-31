from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np
import pandas as pd


def paired_differences(
    summary: pd.DataFrame,
    scenario: str,
    mode_a: str,
    mode_b: str,
    metric: str,
) -> list[float]:
    subset = summary[summary["scenario"] == scenario]
    left = subset[subset["mode"] == mode_a][["seed", metric]].rename(columns={metric: "a"})
    right = subset[subset["mode"] == mode_b][["seed", metric]].rename(columns={metric: "b"})
    paired = left.merge(right, on="seed", how="inner").dropna()
    return [round(float(v), 12) for v in (paired["a"] - paired["b"]).tolist()]


def bootstrap_ci(
    values: list[float] | np.ndarray,
    seed: int = 0,
    n: int = 2000,
    alpha: float = 0.05,
) -> tuple[float, float]:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return (math.nan, math.nan)
    if np.allclose(arr, arr[0]):
        v = float(arr[0])
        return (v, v)
    rng = np.random.default_rng(seed)
    sample_idx = rng.integers(0, arr.size, size=(n, arr.size))
    means = np.mean(arr[sample_idx], axis=1)
    low, high = np.quantile(means, [alpha * 0.5, 1.0 - alpha * 0.5])
    return (float(low), float(high))


def holm_adjust(p_values: list[float] | np.ndarray) -> list[float]:
    p = np.asarray(p_values, dtype=float)
    if p.size == 0:
        return []
    order = np.argsort(p)
    adjusted_sorted = np.empty_like(p)
    running = 0.0
    m = len(p)
    for rank, idx in enumerate(order):
        adjusted = min(1.0, (m - rank) * p[idx])
        running = max(running, adjusted)
        adjusted_sorted[rank] = running
    out = np.empty_like(p)
    out[order] = adjusted_sorted
    return [float(np.clip(v, 0.0, 1.0)) for v in out]


def normal_approx_p_value(differences: list[float] | np.ndarray) -> float:
    arr = np.asarray(differences, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size < 2:
        return math.nan
    std = float(np.std(arr, ddof=1))
    if std <= 1e-12:
        return 0.0 if abs(float(np.mean(arr))) > 1e-12 else 1.0
    z = float(np.mean(arr)) / (std / math.sqrt(arr.size))
    return float(2.0 * (1.0 - NormalDist().cdf(abs(z))))


def paired_comparison_table(
    summary: pd.DataFrame,
    reference_mode: str = "hybrid",
    baseline_modes: tuple[str, ...] | None = None,
    metrics: tuple[str, ...] = (
        "collected_ratio",
        "path_to_80_m",
        "auc_collected_by_path",
        "false_visits",
        "brier_score",
    ),
) -> pd.DataFrame:
    rows: list[dict] = []
    raw_p_values: list[float] = []
    for scenario in sorted(summary["scenario"].dropna().unique()):
        scenario_modes = tuple(
            mode
            for mode in sorted(summary.loc[summary["scenario"] == scenario, "mode"].dropna().unique())
            if mode != reference_mode
        )
        modes_to_compare = baseline_modes if baseline_modes is not None else scenario_modes
        for metric in metrics:
            if metric not in summary.columns:
                continue
            for baseline in modes_to_compare:
                diffs = paired_differences(summary, scenario, reference_mode, baseline, metric)
                finite = [v for v in diffs if math.isfinite(v)]
                if not finite:
                    continue
                ci_low, ci_high = bootstrap_ci(finite)
                p_value = normal_approx_p_value(finite)
                raw_p_values.append(p_value)
                rows.append({
                    "scenario": scenario,
                    "metric": metric,
                    "mode_a": reference_mode,
                    "mode_b": baseline,
                    "paired_runs": len(finite),
                    "mean_difference": float(np.mean(finite)),
                    "ci95_low": ci_low,
                    "ci95_high": ci_high,
                    "p_value": p_value,
                })
    adjusted = holm_adjust(raw_p_values)
    for row, p_adj in zip(rows, adjusted):
        row["p_holm"] = p_adj
    return pd.DataFrame(rows)
