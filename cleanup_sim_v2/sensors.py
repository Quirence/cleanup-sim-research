from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import SensorConfig, SensorSuiteConfig, WorldConfig
from .world import DebrisField


@dataclass(frozen=True)
class Detection:
    sensor: str
    position: np.ndarray
    confidence: float
    source_index: int | None
    is_false: bool
    range_m: float
    localization_sigma_m: float = 0.0


def wrap_angle(angle: np.ndarray | float) -> np.ndarray | float:
    return (angle + np.pi) % (2.0 * np.pi) - np.pi


def in_sensor_fov(points: np.ndarray, pose: np.ndarray, sensor: SensorConfig) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    dx = points[:, 0] - pose[0]
    dy = points[:, 1] - pose[1]
    distance = np.hypot(dx, dy)
    bearing = wrap_angle(np.arctan2(dy, dx) - pose[2])
    mask = (distance <= sensor.range_m) & (np.abs(bearing) <= np.deg2rad(sensor.fov_deg) * 0.5)
    return mask, distance, bearing


def detection_probability(sensor: SensorConfig, distance_m: np.ndarray, size_m: np.ndarray) -> np.ndarray:
    range_term = np.exp(-distance_m / max(sensor.decay_range_m, 1e-9))
    size_term = np.clip(size_m / max(sensor.min_detectable_size_m, 1e-9), 0.15, 1.5)
    return np.clip(sensor.p_detect_max * range_term * size_term, 0.0, 0.98)


def _sector_area(sensor: SensorConfig) -> float:
    return np.deg2rad(sensor.fov_deg) * sensor.range_m * sensor.range_m * 0.5


def _sample_clutter(rng: np.random.Generator, pose: np.ndarray, world: WorldConfig, sensor: SensorConfig) -> list[Detection]:
    n_false = int(rng.poisson(sensor.clutter_rate_per_m2 * _sector_area(sensor)))
    detections: list[Detection] = []
    if n_false <= 0:
        return detections
    ranges = sensor.range_m * np.sqrt(rng.random(n_false))
    bearings = rng.uniform(-0.5 * np.deg2rad(sensor.fov_deg), 0.5 * np.deg2rad(sensor.fov_deg), size=n_false)
    angles = pose[2] + bearings
    points = np.column_stack([pose[0] + ranges * np.cos(angles), pose[1] + ranges * np.sin(angles)])
    points[:, 0] = np.clip(points[:, 0], 0.0, world.width_m)
    points[:, 1] = np.clip(points[:, 1], 0.0, world.height_m)
    for point, range_m in zip(points, ranges):
        confidence = float(np.clip(rng.normal(0.52, sensor.confidence_sigma), 0.05, 0.92))
        detections.append(
            Detection(
                sensor=sensor.name,
                position=point.astype(float),
                confidence=confidence,
                source_index=None,
                is_false=True,
                range_m=float(range_m),
                localization_sigma_m=float(sensor.localization_sigma_m + sensor.localization_sigma_per_m * range_m),
            )
        )
    return detections


def detect_with_sensor(
    rng: np.random.Generator,
    field: DebrisField,
    world: WorldConfig,
    pose: np.ndarray,
    sensor: SensorConfig,
) -> list[Detection]:
    detections = _sample_clutter(rng, pose, world, sensor)
    alive = np.where(~field.collected)[0]
    if alive.size == 0:
        return detections

    points = field.positions[alive]
    visible, distance, _ = in_sensor_fov(points, pose, sensor)
    if not np.any(visible):
        return detections

    visible_ids = alive[visible]
    visible_dist = distance[visible]
    p_detect = detection_probability(sensor, visible_dist, field.sizes_m[visible_ids])
    detected = rng.random(visible_ids.size) < p_detect
    for source_id, dist, p in zip(visible_ids[detected], visible_dist[detected], p_detect[detected]):
        sigma = sensor.localization_sigma_m + sensor.localization_sigma_per_m * dist
        measured = field.positions[source_id] + rng.normal(0.0, sigma, size=2)
        measured[0] = np.clip(measured[0], 0.0, world.width_m)
        measured[1] = np.clip(measured[1], 0.0, world.height_m)
        confidence = float(np.clip(rng.normal(p, sensor.confidence_sigma), 0.05, 0.99))
        detections.append(
            Detection(
                sensor=sensor.name,
                position=measured.astype(float),
                confidence=confidence,
                source_index=int(source_id),
                is_false=False,
                range_m=float(dist),
                localization_sigma_m=float(sigma),
            )
        )
    return detections


def detect_with_suite(
    rng: np.random.Generator,
    field: DebrisField,
    world: WorldConfig,
    pose: np.ndarray,
    suite: SensorSuiteConfig,
) -> list[Detection]:
    detections: list[Detection] = []
    for sensor in suite.sensors:
        detections.extend(detect_with_sensor(rng, field, world, pose, sensor))
    return detections
