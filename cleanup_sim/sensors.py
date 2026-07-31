from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import FusionConfig, SensorConfig
from .mapping import Grid, ProbabilityMap, bayesian_update, cell_indices_for_points
from .world import DebrisField


@dataclass
class Detection:
    sensor: str
    position: np.ndarray
    confidence: float
    source_index: int | None


def _wrap_angle(a: np.ndarray) -> np.ndarray:
    return (a + np.pi) % (2.0 * np.pi) - np.pi


def _sensor_likelihood(sensor: SensorConfig, distance: np.ndarray, bearing: np.ndarray) -> np.ndarray:
    radial = 1.0 / (1.0 + np.exp((distance - sensor.det_center) / sensor.det_kappa))
    sigma = np.deg2rad(sensor.bearing_sigma_deg)
    angular = np.exp(-0.5 * (bearing / max(sigma, 1e-6)) ** 2)
    return np.clip(radial * angular, 1e-4, 0.98)


def visible_mask(grid: Grid, pose: np.ndarray, sensor: SensorConfig) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    dx = grid.xx - pose[0]
    dy = grid.yy - pose[1]
    distance = np.hypot(dx, dy)
    bearing = _wrap_angle(np.arctan2(dy, dx) - pose[2])
    mask = (distance <= sensor.range_m) & (np.abs(bearing) <= np.deg2rad(sensor.fov_deg) * 0.5)
    return mask, distance, bearing


def apply_sensor_update(
    rng: np.random.Generator,
    prob_map: ProbabilityMap,
    field: DebrisField,
    pose: np.ndarray,
    sensor: SensorConfig,
) -> list[Detection]:
    mask, distance, bearing = visible_mask(prob_map.grid, pose, sensor)
    if not np.any(mask):
        return []

    available = np.where(~field.collected)[0]
    occ = np.zeros_like(prob_map.belief, dtype=bool)
    if available.size:
        iy, ix = cell_indices_for_points(prob_map.grid, field.positions[available])
        occ[iy, ix] = True

    p_occ = _sensor_likelihood(sensor, distance, bearing)
    p_free = np.full_like(p_occ, sensor.p_false, dtype=float)
    z = np.zeros_like(mask, dtype=bool)
    draws_occ = rng.random(mask.shape)
    z[mask & occ] = draws_occ[mask & occ] < p_occ[mask & occ]
    draws_free = rng.random(mask.shape)
    z[mask & ~occ] = draws_free[mask & ~occ] < p_free[mask & ~occ]

    before = prob_map.belief[mask]
    after = bayesian_update(before, z[mask], p_occ[mask], p_free[mask])
    prob_map.belief[mask] = after

    detections: list[Detection] = []
    positive_cells = np.argwhere(mask & z)
    for iy_cell, ix_cell in positive_cells:
        cell_pos = np.array([prob_map.grid.x_centers[ix_cell], prob_map.grid.y_centers[iy_cell]])
        source_index = None
        if available.size:
            d_to_debris = np.linalg.norm(field.positions[available] - cell_pos, axis=1)
            nearest_id = int(np.argmin(d_to_debris))
            if d_to_debris[nearest_id] <= max(3.0, sensor.localization_sigma_m * 2.0):
                source_index = int(available[nearest_id])
                base_pos = field.positions[source_index]
            else:
                base_pos = cell_pos
        else:
            base_pos = cell_pos
        measured = base_pos + rng.normal(0.0, sensor.localization_sigma_m, size=2)
        confidence = float(prob_map.belief[iy_cell, ix_cell])
        detections.append(Detection(sensor=sensor.name, position=measured, confidence=confidence, source_index=source_index))
    return detections


def apply_fusion_update(
    rng: np.random.Generator,
    prob_map: ProbabilityMap,
    field: DebrisField,
    pose: np.ndarray,
    fusion: FusionConfig,
) -> list[Detection]:
    detections = []
    detections.extend(apply_sensor_update(rng, prob_map, field, pose, fusion.radar))
    detections.extend(apply_sensor_update(rng, prob_map, field, pose, fusion.camera))
    return detections
