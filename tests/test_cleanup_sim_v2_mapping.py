from __future__ import annotations

import numpy as np

from cleanup_sim_v2.config import GridConfig, HydroConfig, SensorConfig
from cleanup_sim_v2.mapping import (
    DensityMap,
    entropy,
    make_grid,
    predict_density_map,
    suppress_collected_area,
    update_density_map,
    visible_cell_mask,
)
from cleanup_sim_v2.sensors import Detection
from cleanup_sim_v2.world import WorldConfig


def _grid(nx: int = 20, ny: int = 20, width_m: float = 20.0, height_m: float = 20.0):
    return make_grid(WorldConfig(width_m=width_m, height_m=height_m), GridConfig(nx=nx, ny=ny))


def _sensor(**overrides) -> SensorConfig:
    base = dict(
        name="camera",
        range_m=20.0,
        fov_deg=90.0,
        p_detect_max=1.0,
        decay_range_m=1e9,
        min_detectable_size_m=0.01,
        localization_sigma_m=0.0,
        localization_sigma_per_m=0.0,
        clutter_rate_per_m2=0.0,
        confidence_sigma=0.0,
    )
    base.update(overrides)
    return SensorConfig(**base)


def test_entropy_is_maximal_near_half_and_low_near_extremes() -> None:
    h = entropy(np.array([0.001, 0.5, 0.999]))
    assert h[1] > h[0]
    assert h[1] > h[2]
    assert h[0] > 0.0
    assert h[2] > 0.0


def test_predict_density_map_is_identity_with_no_velocity_no_diffusion_no_decay() -> None:
    grid = _grid()
    density_map = DensityMap(grid=grid, expected_count=np.full(grid.xx.shape, 1.0))
    before = density_map.expected_count.copy()

    predict_density_map(density_map, HydroConfig(), GridConfig(prediction_decay_per_step=0.0), dt_s=1.0)

    assert np.allclose(density_map.expected_count, before)


def test_predict_density_map_decay_scales_total_mass() -> None:
    grid = _grid()
    density_map = DensityMap(grid=grid, expected_count=np.full(grid.xx.shape, 2.0))
    total_before = float(density_map.expected_count.sum())

    predict_density_map(density_map, HydroConfig(), GridConfig(prediction_decay_per_step=0.1), dt_s=1.0)

    assert np.isclose(float(density_map.expected_count.sum()), total_before * 0.9)


def test_predict_density_map_advects_mass_in_the_current_direction() -> None:
    grid = _grid(nx=40, ny=40, width_m=40.0, height_m=40.0)
    expected_count = np.zeros(grid.xx.shape)
    # A single sharp peak in the middle of the grid.
    mid_iy, mid_ix = grid.xx.shape[0] // 2, grid.xx.shape[1] // 2
    expected_count[mid_iy, mid_ix] = 100.0
    density_map = DensityMap(grid=grid, expected_count=expected_count)
    peak_x_before = float(grid.x_centers[np.unravel_index(np.argmax(density_map.expected_count), density_map.expected_count.shape)[1]])

    hydro = HydroConfig(current_x_mps=2.0, current_y_mps=0.0)
    predict_density_map(density_map, hydro, GridConfig(prediction_decay_per_step=0.0), dt_s=1.0)

    peak_x_after = float(grid.x_centers[np.unravel_index(np.argmax(density_map.expected_count), density_map.expected_count.shape)[1]])
    # A positive x-current must move the peak toward larger x.
    assert peak_x_after > peak_x_before


def test_visible_cell_mask_matches_range_and_fov() -> None:
    grid = _grid()
    sensor = _sensor(range_m=5.0, fov_deg=90.0)
    pose = np.array([10.0, 10.0, 0.0])

    mask = visible_cell_mask(grid, pose, sensor)

    # Cell centers are at 0.5, 1.5, ..., 19.5 (nx=20 over a 20 m world); pick targets
    # exactly on the grid so the tolerance can be tight.
    def _cell(x: float, y: float) -> np.ndarray:
        return (np.abs(grid.xx - x) < 0.1) & (np.abs(grid.yy - y) < 0.1)

    # Within range (dist ~3.5 m <= 5 m) and directly ahead (+x, heading=0) -> visible.
    assert np.any(mask & _cell(13.5, 10.5))
    # Directly behind the sensor, also within range (dist ~3.5 m) -> excluded by FOV.
    assert not np.any(mask & _cell(6.5, 10.5))
    # Ahead but beyond range (dist ~9 m > 5 m) -> excluded by range even though within FOV.
    assert not np.any(mask & _cell(19.5, 10.5))


def test_update_density_map_increases_expected_count_near_true_detection() -> None:
    grid = _grid()
    density_map = DensityMap(grid=grid, expected_count=np.full(grid.xx.shape, 0.01))
    sensor = _sensor()
    pose = np.array([10.0, 10.0, 0.0])
    detection_point = np.array([12.0, 10.0])
    det = Detection(
        sensor="camera",
        position=detection_point,
        confidence=0.9,
        source_index=0,
        is_false=False,
        range_m=2.0,
        localization_sigma_m=0.5,
    )

    before_near = float(density_map.expected_count[
        (np.abs(grid.yy - 10.0) <= 0.5) & (np.abs(grid.xx - 12.0) <= 0.5)
    ].mean())

    update_density_map(density_map, pose, (sensor,), [det])

    after_near = float(density_map.expected_count[
        (np.abs(grid.yy - 10.0) <= 0.5) & (np.abs(grid.xx - 12.0) <= 0.5)
    ].mean())
    assert after_near > before_near


def test_update_density_map_decays_expected_count_in_seen_but_empty_cells() -> None:
    grid = _grid()
    density_map = DensityMap(grid=grid, expected_count=np.full(grid.xx.shape, 1.0))
    sensor = _sensor(p_detect_max=0.9)
    pose = np.array([10.0, 10.0, 0.0])

    update_density_map(density_map, pose, (sensor,), [])

    far_point = (np.abs(grid.xx - 0.5) <= 0.5) & (np.abs(grid.yy - 0.5) <= 0.5)
    near_point = (np.abs(grid.xx - 10.0) <= 0.5) & (np.abs(grid.yy - 10.0) <= 0.5)
    # Cells in the sensor's FOV with no detection get a small negative-evidence
    # decay; cells outside the FOV are untouched.
    assert float(density_map.expected_count[near_point].mean()) < 1.0
    assert np.isclose(float(density_map.expected_count[far_point].mean()), 1.0)


def test_suppress_collected_area_scales_down_only_nearby_cells() -> None:
    grid = _grid()
    density_map = DensityMap(grid=grid, expected_count=np.full(grid.xx.shape, 4.0))

    suppress_collected_area(density_map, np.array([10.0, 10.0]), radius_m=1.0)

    near = (np.abs(grid.xx - 10.0) <= 0.5) & (np.abs(grid.yy - 10.0) <= 0.5)
    far = (np.abs(grid.xx - 19.0) <= 0.5) & (np.abs(grid.yy - 19.0) <= 0.5)
    assert np.allclose(density_map.expected_count[near], 1.0)
    assert np.allclose(density_map.expected_count[far], 4.0)
