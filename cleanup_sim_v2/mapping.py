from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import shift as ndi_shift

from .config import GridConfig, HydroConfig, SensorConfig, WorldConfig
from .hydrodynamics import ambient_velocity
from .sensors import Detection, in_sensor_fov


EPS = 1e-9


@dataclass(frozen=True)
class Grid:
    x_edges: np.ndarray
    y_edges: np.ndarray
    x_centers: np.ndarray
    y_centers: np.ndarray
    xx: np.ndarray
    yy: np.ndarray

    @property
    def dx(self) -> float:
        return float(np.mean(np.diff(self.x_edges)))

    @property
    def dy(self) -> float:
        return float(np.mean(np.diff(self.y_edges)))


@dataclass
class DensityMap:
    grid: Grid
    expected_count: np.ndarray

    @property
    def occupancy(self) -> np.ndarray:
        return 1.0 - np.exp(-np.clip(self.expected_count, 0.0, None))


def make_grid(world: WorldConfig, cfg: GridConfig) -> Grid:
    x_edges = np.linspace(0.0, world.width_m, cfg.nx + 1)
    y_edges = np.linspace(0.0, world.height_m, cfg.ny + 1)
    x_centers = 0.5 * (x_edges[:-1] + x_edges[1:])
    y_centers = 0.5 * (y_edges[:-1] + y_edges[1:])
    xx, yy = np.meshgrid(x_centers, y_centers, indexing="xy")
    return Grid(x_edges=x_edges, y_edges=y_edges, x_centers=x_centers, y_centers=y_centers, xx=xx, yy=yy)


def init_density_map(grid: Grid, grid_cfg: GridConfig, world: WorldConfig) -> DensityMap:
    prior = grid_cfg.prior_expected_count_per_cell
    if prior is None:
        prior = world.n_debris / float(grid.xx.size)
    return DensityMap(grid=grid, expected_count=np.full(grid.xx.shape, prior, dtype=float))


def entropy(occupancy: np.ndarray) -> np.ndarray:
    b = np.clip(occupancy, EPS, 1.0 - EPS)
    return -(b * np.log(b) + (1.0 - b) * np.log(1.0 - b))


def predict_density_map(density_map: DensityMap, hydro: HydroConfig, grid_cfg: GridConfig, dt_s: float) -> None:
    vel = ambient_velocity(hydro)
    if np.linalg.norm(vel) > 1e-12:
        shift_yx = (vel[1] * dt_s / density_map.grid.dy, vel[0] * dt_s / density_map.grid.dx)
        density_map.expected_count = ndi_shift(
            density_map.expected_count,
            shift=shift_yx,
            order=1,
            mode="nearest",
            prefilter=False,
        )
    if hydro.diffusivity_m2_s > 0.0:
        # A light numerical diffusion proxy; physical diffusion is already applied to particles.
        density_map.expected_count = (
            0.985 * density_map.expected_count
            + 0.00375 * np.roll(density_map.expected_count, 1, axis=0)
            + 0.00375 * np.roll(density_map.expected_count, -1, axis=0)
            + 0.00375 * np.roll(density_map.expected_count, 1, axis=1)
            + 0.00375 * np.roll(density_map.expected_count, -1, axis=1)
        )
    density_map.expected_count *= max(0.0, 1.0 - grid_cfg.prediction_decay_per_step)
    density_map.expected_count = np.clip(density_map.expected_count, 0.0, None)


def visible_cell_mask(grid: Grid, pose: np.ndarray, sensor: SensorConfig) -> np.ndarray:
    points = np.column_stack([grid.xx.ravel(), grid.yy.ravel()])
    mask, _, _ = in_sensor_fov(points, pose, sensor)
    return mask.reshape(grid.xx.shape)


def _add_detection_kernel(density_map: DensityMap, det: Detection, sensor: SensorConfig) -> None:
    sigma = max(sensor.localization_sigma_m + sensor.localization_sigma_per_m * det.range_m, 0.5)
    radius = max(2.5 * sigma, density_map.grid.dx)
    dist2 = (density_map.grid.xx - det.position[0]) ** 2 + (density_map.grid.yy - det.position[1]) ** 2
    mask = dist2 <= radius * radius
    if not np.any(mask):
        return
    kernel = np.exp(-0.5 * dist2[mask] / (sigma * sigma))
    kernel_sum = float(kernel.sum())
    if kernel_sum <= EPS:
        return
    confidence = float(np.clip(det.confidence, 0.01, 0.99))
    increment = -np.log(1.0 - confidence) * (0.75 if det.sensor == "camera" else 0.55)
    density_map.expected_count[mask] += increment * kernel / kernel_sum


def update_density_map(
    density_map: DensityMap,
    pose: np.ndarray,
    sensors: tuple[SensorConfig, ...],
    detections: list[Detection],
) -> float:
    before_entropy = float(np.mean(entropy(density_map.occupancy)))
    for sensor in sensors:
        mask = visible_cell_mask(density_map.grid, pose, sensor)
        # No-observation evidence is weak but sensor-dependent: object-level detectors do not prove empty water.
        missed_detection_factor = 1.0 - 0.025 * np.clip(sensor.p_detect_max, 0.0, 0.98)
        density_map.expected_count[mask] *= missed_detection_factor
    by_name = {sensor.name: sensor for sensor in sensors}
    for det in detections:
        _add_detection_kernel(density_map, det, by_name[det.sensor])
    density_map.expected_count = np.clip(density_map.expected_count, 0.0, None)
    after_entropy = float(np.mean(entropy(density_map.occupancy)))
    return before_entropy - after_entropy


def suppress_collected_area(density_map: DensityMap, position: np.ndarray, radius_m: float) -> None:
    dist = np.hypot(density_map.grid.xx - position[0], density_map.grid.yy - position[1])
    density_map.expected_count[dist <= radius_m] *= 0.25
