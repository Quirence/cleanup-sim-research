from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .mapping import entropy


@dataclass
class TimeSeries:
    time_s: list[float]
    path_m: list[float]
    collected: list[int]
    false_visits: list[int]
    planner_mode: list[str]


def path_length(path: np.ndarray) -> float:
    if len(path) < 2:
        return 0.0
    return float(np.sum(np.linalg.norm(np.diff(path, axis=0), axis=1)))


def threshold_crossing(xs: list[float], ys: list[int], total: int, ratio: float) -> float | None:
    target = ratio * total
    for x, y in zip(xs, ys):
        if y >= target:
            return float(x)
    return None


def value_at_budget(xs: list[float], ys: list[float], budget: float) -> float:
    value = ys[0] if ys else 0.0
    for x, y in zip(xs, ys):
        if x <= budget:
            value = y
        else:
            break
    return float(value)


def auc_collected_ratio(xs: list[float], ratios: list[float], budget: float) -> float:
    if not xs or not ratios or budget <= 0:
        return 0.0
    x = [0.0]
    y = [ratios[0]]
    for xi, yi in zip(xs, ratios):
        if xi <= budget:
            x.append(float(xi))
            y.append(float(yi))
        else:
            break
    if x[-1] < budget:
        x.append(float(budget))
        y.append(y[-1])
    return float(np.trapezoid(y, x) / budget)


def map_quality(belief: np.ndarray, true_occ: np.ndarray, threshold: float = 0.5) -> dict:
    pred = belief >= threshold
    tp = int(np.logical_and(pred, true_occ).sum())
    fp = int(np.logical_and(pred, ~true_occ).sum())
    fn = int(np.logical_and(~pred, true_occ).sum())
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    f1 = 2.0 * precision * recall / max(1e-9, precision + recall)
    iou = tp / max(1, tp + fp + fn)
    brier = float(np.mean((belief - true_occ.astype(float)) ** 2))
    return {
        "map_precision": precision,
        "map_recall": recall,
        "map_f1": f1,
        "map_iou": iou,
        "brier_score": brier,
        "final_entropy": float(np.mean(entropy(belief))),
    }


def _prefixed_map_quality(quality: dict, prefix: str) -> dict:
    return {
        f"{prefix}_map_precision": quality["map_precision"],
        f"{prefix}_map_recall": quality["map_recall"],
        f"{prefix}_map_f1": quality["map_f1"],
        f"{prefix}_map_iou": quality["map_iou"],
        f"{prefix}_brier_score": quality["brier_score"],
    }


def count_map_stats(count_map: np.ndarray, prefix: str) -> dict:
    counts = np.asarray(count_map, dtype=int)
    total = int(counts.sum())
    occupied = int((counts > 0).sum())
    multi = int((counts > 1).sum())
    max_count = int(counts.max()) if counts.size else 0
    return {
        f"{prefix}_debris_count_total": total,
        f"{prefix}_occupied_cells": occupied,
        f"{prefix}_multi_debris_cells": multi,
        f"{prefix}_max_cell_count": max_count,
        f"{prefix}_mean_count_per_occupied_cell": float(total / occupied) if occupied > 0 else 0.0,
        f"{prefix}_occupancy_collision_ratio": float((total - occupied) / total) if total > 0 else 0.0,
    }


def summarize_run(
    scenario: str,
    mode: str,
    seed: int,
    total_debris: int,
    collected_count: int,
    collected_mass_kg: float,
    total_mass_kg: float,
    path_m: float,
    path_budget_m: float | None,
    sim_time_s: float,
    unload_events: int,
    false_visits: int,
    stop_reason: str,
    target_confirmed: int,
    target_route_attempts: int,
    target_visit_successes: int,
    target_visit_false: int,
    series: TimeSeries,
    belief: np.ndarray,
    true_occ: np.ndarray,
    residual_true_occ: np.ndarray | None = None,
    true_count: np.ndarray | None = None,
    residual_true_count: np.ndarray | None = None,
) -> dict:
    residual_occ = true_occ if residual_true_occ is None else residual_true_occ
    initial_count = true_occ.astype(int) if true_count is None else true_count
    residual_count = residual_occ.astype(int) if residual_true_count is None else residual_true_count
    initial_quality = map_quality(belief, true_occ)
    residual_quality = map_quality(belief, residual_occ)
    collected_ratios = [count / max(1, total_debris) for count in series.collected]
    auc_budget_m = path_budget_m if path_budget_m is not None else path_m
    out = {
        "scenario": scenario,
        "mode": mode,
        "seed": seed,
        "total_debris": total_debris,
        "collected": collected_count,
        "collected_ratio": collected_count / max(1, total_debris),
        "collected_mass_kg": collected_mass_kg,
        "mass_ratio": collected_mass_kg / max(1e-9, total_mass_kg),
        "path_length_m": path_m,
        "sim_time_s": sim_time_s,
        "unload_events": unload_events,
        "false_visits": false_visits,
        "stop_reason": stop_reason,
        "target_confirmed": target_confirmed,
        "target_route_attempts": target_route_attempts,
        "target_visit_successes": target_visit_successes,
        "target_visit_false": target_visit_false,
        "target_precision": target_visit_successes / max(1, target_visit_successes + target_visit_false),
        "time_to_50_s": threshold_crossing(series.time_s, series.collected, total_debris, 0.50),
        "time_to_80_s": threshold_crossing(series.time_s, series.collected, total_debris, 0.80),
        "time_to_95_s": threshold_crossing(series.time_s, series.collected, total_debris, 0.95),
        "path_to_50_m": threshold_crossing(series.path_m, series.collected, total_debris, 0.50),
        "path_to_80_m": threshold_crossing(series.path_m, series.collected, total_debris, 0.80),
        "path_to_95_m": threshold_crossing(series.path_m, series.collected, total_debris, 0.95),
        "auc_collected_by_path": auc_collected_ratio(series.path_m, collected_ratios, auc_budget_m),
    }
    for budget_m in [2000, 4000, 6000, 8000, 10000, 12000]:
        out[f"collected_ratio_at_{budget_m // 1000}km"] = value_at_budget(
            series.path_m,
            collected_ratios,
            float(budget_m),
        )
    out.update(_prefixed_map_quality(initial_quality, "initial"))
    out.update(_prefixed_map_quality(residual_quality, "residual"))
    out.update(count_map_stats(initial_count, "initial"))
    out.update(count_map_stats(residual_count, "residual"))
    out.update({
        "map_precision": residual_quality["map_precision"],
        "map_recall": residual_quality["map_recall"],
        "map_f1": residual_quality["map_f1"],
        "map_iou": residual_quality["map_iou"],
        "brier_score": residual_quality["brier_score"],
        "final_entropy": residual_quality["final_entropy"],
    })
    return out
