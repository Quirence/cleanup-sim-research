from __future__ import annotations

import numpy as np

from cleanup_sim_v2.mapping import DensityMap, Grid
from cleanup_sim_v2.metrics import (
    auc_by_path,
    map_quality,
    occupancy_from_count,
    sensor_metrics,
    value_at_path,
)


def _tiny_grid() -> Grid:
    x_edges = np.array([0.0, 1.0, 2.0])
    y_edges = np.array([0.0, 1.0, 2.0])
    x_centers = np.array([0.5, 1.5])
    y_centers = np.array([0.5, 1.5])
    xx, yy = np.meshgrid(x_centers, y_centers, indexing="xy")
    return Grid(x_edges=x_edges, y_edges=y_edges, x_centers=x_centers, y_centers=y_centers, xx=xx, yy=yy)


def test_occupancy_from_count_thresholds_at_zero() -> None:
    counts = np.array([[0, 1], [3, 0]])
    assert np.array_equal(occupancy_from_count(counts), np.array([[False, True], [True, False]]))


def test_map_quality_perfect_prediction_gives_f1_and_iou_one() -> None:
    grid = _tiny_grid()
    true_counts = np.array([[0.0, 5.0], [2.0, 0.0]])
    # expected_count large enough that occupancy = 1 - exp(-x) rounds to >= 0.5 exactly
    # where true_counts > 0, and stays 0 (< 0.5) elsewhere.
    density_map = DensityMap(grid=grid, expected_count=np.array([[0.0, 5.0], [2.0, 0.0]]))

    quality = map_quality(density_map, true_counts)

    assert quality["map_precision"] == 1.0
    assert quality["map_recall"] == 1.0
    assert quality["map_f1"] == 1.0
    assert quality["map_iou"] == 1.0
    assert quality["count_mae"] == 0.0
    assert quality["map_brier"] < 0.01


def test_map_quality_penalizes_false_positive_and_false_negative_cells() -> None:
    grid = _tiny_grid()
    # True debris only in cell (0, 1); predicted occupancy high in (0, 1) and (1, 0),
    # low in (1, 1) which is truly occupied but missed.
    true_counts = np.array([[0.0, 5.0], [4.0, 0.0]])
    density_map = DensityMap(grid=grid, expected_count=np.array([[0.0, 5.0], [0.0, 5.0]]))

    quality = map_quality(density_map, true_counts)

    # tp=1 (0,1), fp=1 (1,1 predicted occupied but truly empty), fn=1 (1,0 truly
    # occupied but predicted empty) -> precision=recall=iou=1/2, f1=1/2.
    assert quality["map_precision"] == 0.5
    assert quality["map_recall"] == 0.5
    assert quality["map_f1"] == 0.5
    assert quality["map_iou"] == 1.0 / 3.0
    assert quality["count_mae"] > 0.0


def test_auc_by_path_linear_ramp_matches_triangle_area() -> None:
    # Linear ramp from (0, 0) to (10, 1): area under curve is a triangle of area
    # 0.5 * 10 * 1 = 5, normalized by budget 10 -> 0.5.
    auc = auc_by_path(path_m=[0.0, 10.0], ratios=[0.0, 1.0], budget_m=10.0)
    assert np.isclose(auc, 0.5)


def test_auc_by_path_holds_last_value_flat_beyond_final_sample() -> None:
    # Ramp reaches 1.0 at x=5, then holds flat to budget=10: triangle(0..5)=2.5 +
    # rectangle(5..10, height 1)=5, total 7.5, normalized by budget 10 -> 0.75.
    auc = auc_by_path(path_m=[0.0, 5.0], ratios=[0.0, 1.0], budget_m=10.0)
    assert np.isclose(auc, 0.75)


def test_auc_by_path_empty_input_returns_zero() -> None:
    assert auc_by_path([], [], 10.0) == 0.0


def test_value_at_path_interpolates_between_samples() -> None:
    value = value_at_path(path_m=[0.0, 10.0], ratios=[0.0, 1.0], budget_m=5.0)
    assert np.isclose(value, 0.5)


def test_value_at_path_empty_input_returns_zero() -> None:
    assert value_at_path([], [], 5.0) == 0.0


def _record(sensor: str, is_false: bool, source_index: int | None, range_m: float) -> dict:
    return {"sensor": sensor, "is_false": is_false, "source_index": source_index, "range_m": range_m}


def test_sensor_metrics_empty_records_returns_zeroed_dict() -> None:
    metrics = sensor_metrics([], total_debris=5)
    assert metrics["detection_precision"] == 0.0
    assert metrics["detection_recall"] == 0.0
    assert metrics["false_detection_count"] == 0
    assert metrics["true_detection_count"] == 0


def test_sensor_metrics_computes_precision_recall_and_range_bins() -> None:
    records = [
        _record("camera", False, 0, range_m=5.0),   # true, near
        _record("camera", False, 1, range_m=20.0),  # true, mid
        _record("camera", True, None, range_m=5.0),  # false, near
        _record("radar", False, 0, range_m=40.0),    # true (duplicate source), far
        _record("radar", True, None, range_m=40.0),  # false, far
    ]

    metrics = sensor_metrics(records, total_debris=4)

    # 3 true / 5 total detections overall; 2 distinct source ids detected out of 4 debris.
    assert metrics["detection_precision"] == 3 / 5
    assert metrics["detection_recall"] == 2 / 4
    assert metrics["true_detection_count"] == 3
    assert metrics["false_detection_count"] == 2

    assert metrics["camera_detection_precision"] == 2 / 3
    assert metrics["camera_true_detection_count"] == 2
    assert metrics["radar_detection_precision"] == 1 / 2
    assert metrics["radar_true_detection_count"] == 1

    assert metrics["near_range_detection_count"] == 2
    assert metrics["mid_range_detection_count"] == 1
    assert metrics["far_range_detection_count"] == 2
    assert metrics["far_range_detection_precision"] == 1 / 2
