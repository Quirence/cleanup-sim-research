from __future__ import annotations

import numpy as np

from .mapping import DensityMap


def occupancy_from_count(counts: np.ndarray) -> np.ndarray:
    return counts > 0


def map_quality(density_map: DensityMap, true_counts: np.ndarray) -> dict:
    true_occ = occupancy_from_count(true_counts)
    pred_occ = density_map.occupancy >= 0.5
    tp = int(np.sum(pred_occ & true_occ))
    fp = int(np.sum(pred_occ & ~true_occ))
    fn = int(np.sum(~pred_occ & true_occ))
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    f1 = 2.0 * precision * recall / max(1e-9, precision + recall)
    iou = tp / max(1, tp + fp + fn)
    brier = float(np.mean((density_map.occupancy - true_occ.astype(float)) ** 2))
    count_mae = float(np.mean(np.abs(density_map.expected_count - true_counts.astype(float))))
    return {
        "map_precision": precision,
        "map_recall": recall,
        "map_f1": f1,
        "map_iou": iou,
        "map_brier": brier,
        "count_mae": count_mae,
    }


def auc_by_path(path_m: list[float], ratios: list[float], budget_m: float) -> float:
    if not path_m or not ratios:
        return 0.0
    x = np.asarray(path_m, dtype=float)
    y = np.asarray(ratios, dtype=float)
    order = np.argsort(x)
    x = x[order]
    y = y[order]
    if x[0] > 0.0:
        x = np.insert(x, 0, 0.0)
        y = np.insert(y, 0, y[0])
    if x[-1] < budget_m:
        x = np.append(x, budget_m)
        y = np.append(y, y[-1])
    else:
        y_at_budget = np.interp(budget_m, x, y)
        keep = x < budget_m
        x = np.append(x[keep], budget_m)
        y = np.append(y[keep], y_at_budget)
    return float(np.trapezoid(y, x) / max(1e-9, budget_m))


def value_at_path(path_m: list[float], ratios: list[float], budget_m: float) -> float:
    if not path_m or not ratios:
        return 0.0
    return float(np.interp(budget_m, np.asarray(path_m, dtype=float), np.asarray(ratios, dtype=float)))


def sensor_metrics(detection_records: list[dict], total_debris: int) -> dict:
    if not detection_records:
        return {
            "detection_precision": 0.0,
            "detection_recall": 0.0,
            "false_detection_count": 0,
            "true_detection_count": 0,
            "camera_detection_precision": 0.0,
            "camera_detection_recall": 0.0,
            "radar_detection_precision": 0.0,
            "radar_detection_recall": 0.0,
            "near_range_detection_precision": 0.0,
            "mid_range_detection_precision": 0.0,
            "far_range_detection_precision": 0.0,
        }
    true_records = [d for d in detection_records if not d["is_false"]]
    false_records = [d for d in detection_records if d["is_false"]]
    detected_ids = {int(d["source_index"]) for d in true_records if d["source_index"] is not None}
    out = {
        "detection_precision": len(true_records) / max(1, len(detection_records)),
        "detection_recall": len(detected_ids) / max(1, total_debris),
        "false_detection_count": len(false_records),
        "true_detection_count": len(true_records),
    }
    for sensor_name in ("camera", "radar"):
        sensor_records = [d for d in detection_records if d["sensor"] == sensor_name]
        sensor_true = [d for d in sensor_records if not d["is_false"]]
        sensor_ids = {int(d["source_index"]) for d in sensor_true if d["source_index"] is not None}
        out[f"{sensor_name}_detection_precision"] = len(sensor_true) / max(1, len(sensor_records))
        out[f"{sensor_name}_detection_recall"] = len(sensor_ids) / max(1, total_debris)
        out[f"{sensor_name}_false_detection_count"] = len(sensor_records) - len(sensor_true)
        out[f"{sensor_name}_true_detection_count"] = len(sensor_true)

    range_bins = {
        "near": (0.0, 15.0),
        "mid": (15.0, 30.0),
        "far": (30.0, np.inf),
    }
    for name, (lo, hi) in range_bins.items():
        records = [d for d in detection_records if lo <= float(d.get("range_m", 0.0)) < hi]
        true_in_bin = [d for d in records if not d["is_false"]]
        out[f"{name}_range_detection_precision"] = len(true_in_bin) / max(1, len(records))
        out[f"{name}_range_detection_count"] = len(records)
    return out
