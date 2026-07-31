from __future__ import annotations

import math
from statistics import NormalDist
import zlib

import numpy as np
import pandas as pd


def paired_metric_frame(
    summary: pd.DataFrame,
    scenario: str,
    mode_a: str,
    mode_b: str,
    metric: str,
) -> pd.DataFrame:
    subset = summary[summary["scenario"] == scenario]
    left = subset[subset["mode"] == mode_a][["seed", metric]].rename(columns={metric: "a"})
    right = subset[subset["mode"] == mode_b][["seed", metric]].rename(columns={metric: "b"})
    return left.merge(right, on="seed", how="inner")


def paired_differences(
    summary: pd.DataFrame,
    scenario: str,
    mode_a: str,
    mode_b: str,
    metric: str,
) -> list[float]:
    paired = paired_metric_frame(summary, scenario, mode_a, mode_b, metric).dropna()
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


def paired_permutation_p_value(
    differences: list[float] | np.ndarray,
    seed: int = 0,
    exact_max_n: int = 16,
    n_resamples: int = 20000,
) -> float:
    arr = np.asarray(differences, dtype=float)
    arr = arr[np.isfinite(arr)]
    arr = arr[np.abs(arr) > 1e-12]
    if arr.size == 0:
        return 1.0
    observed = abs(float(np.mean(arr)))
    if arr.size <= exact_max_n:
        signs = np.array(np.meshgrid(*([[-1.0, 1.0]] * arr.size))).T.reshape(-1, arr.size)
        stats = np.abs(np.mean(signs * arr, axis=1))
        return float(np.mean(stats >= observed - 1e-12))
    rng = np.random.default_rng(seed)
    signs = rng.choice(np.array([-1.0, 1.0]), size=(n_resamples, arr.size))
    stats = np.abs(np.mean(signs * arr, axis=1))
    extreme = int(np.sum(stats >= observed - 1e-12))
    return float((extreme + 1) / (n_resamples + 1))


def cohen_dz(differences: list[float] | np.ndarray) -> float:
    arr = np.asarray(differences, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size < 2:
        return math.nan
    std = float(np.std(arr, ddof=1))
    if std <= 1e-12:
        return math.copysign(math.inf, float(np.mean(arr))) if abs(float(np.mean(arr))) > 1e-12 else 0.0
    return float(np.mean(arr) / std)


def _average_ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values)
    ranks = np.empty(values.size, dtype=float)
    sorted_values = values[order]
    i = 0
    while i < values.size:
        j = i + 1
        while j < values.size and abs(float(sorted_values[j] - sorted_values[i])) <= 1e-12:
            j += 1
        rank = 0.5 * (i + 1 + j)
        ranks[order[i:j]] = rank
        i = j
    return ranks


def rank_biserial_effect(differences: list[float] | np.ndarray) -> float:
    arr = np.asarray(differences, dtype=float)
    arr = arr[np.isfinite(arr)]
    arr = arr[np.abs(arr) > 1e-12]
    if arr.size == 0:
        return 0.0
    ranks = _average_ranks(np.abs(arr))
    positive = float(np.sum(ranks[arr > 0]))
    negative = float(np.sum(ranks[arr < 0]))
    total = float(np.sum(ranks))
    return float((positive - negative) / total) if total > 0 else 0.0


def _stable_seed(*parts: str) -> int:
    payload = "|".join(parts).encode("utf-8")
    return int(zlib.crc32(payload) & 0xFFFFFFFF)


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
    raw_p_value_rows: list[int] = []
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
                paired = paired_metric_frame(summary, scenario, reference_mode, baseline, metric)
                if paired.empty:
                    continue
                pair_total = int(len(paired))
                mode_a_reached = int(paired["a"].notna().sum())
                mode_b_reached = int(paired["b"].notna().sum())
                both_reached = int(paired[["a", "b"]].dropna().shape[0])
                diffs = [round(float(v), 12) for v in (paired.dropna()["a"] - paired.dropna()["b"]).tolist()]
                finite = [v for v in diffs if math.isfinite(v)]
                ci_low, ci_high = bootstrap_ci(finite)
                permutation_seed = _stable_seed(str(scenario), str(metric), str(reference_mode), str(baseline))
                p_permutation = paired_permutation_p_value(finite, seed=permutation_seed) if finite else math.nan
                p_normal = normal_approx_p_value(finite) if finite else math.nan
                mean_difference = float(np.mean(finite)) if finite else math.nan
                if math.isfinite(p_permutation):
                    raw_p_value_rows.append(len(rows))
                    raw_p_values.append(p_permutation)
                rows.append({
                    "scenario": scenario,
                    "metric": metric,
                    "mode_a": reference_mode,
                    "mode_b": baseline,
                    "paired_total": pair_total,
                    "paired_runs": len(finite),
                    "mode_a_reached": mode_a_reached,
                    "mode_b_reached": mode_b_reached,
                    "both_reached": both_reached,
                    "mode_a_reach_rate": mode_a_reached / max(1, pair_total),
                    "mode_b_reach_rate": mode_b_reached / max(1, pair_total),
                    "censored_pairs": pair_total - both_reached,
                    "mean_difference": mean_difference,
                    "ci95_low": ci_low,
                    "ci95_high": ci_high,
                    "cohen_dz": cohen_dz(finite),
                    "rank_biserial": rank_biserial_effect(finite),
                    "p_value": p_permutation,
                    "p_permutation": p_permutation,
                    "p_normal_approx": p_normal,
                })
    adjusted = holm_adjust(raw_p_values)
    for row in rows:
        row["p_holm"] = math.nan
    for row_idx, p_adj in zip(raw_p_value_rows, adjusted):
        rows[row_idx]["p_holm"] = p_adj
    return pd.DataFrame(rows)
