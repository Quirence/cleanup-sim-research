from __future__ import annotations

import numpy as np

from .config import HydroConfig, WorldConfig
from .world import DebrisField, reflect_bounds


def ambient_velocity(hydro: HydroConfig) -> np.ndarray:
    return np.array([
        hydro.current_x_mps + hydro.windage * hydro.wind_x_mps,
        hydro.current_y_mps + hydro.windage * hydro.wind_y_mps,
    ], dtype=float)


def drift_debris(
    rng: np.random.Generator,
    field: DebrisField,
    world: WorldConfig,
    hydro: HydroConfig,
    dt_s: float,
    robot_pos: np.ndarray | None = None,
) -> None:
    alive = np.where(~field.collected)[0]
    if alive.size == 0:
        return

    velocity = np.tile(ambient_velocity(hydro), (alive.size, 1))
    if hydro.diffusivity_m2_s > 0.0:
        sigma = float(np.sqrt(2.0 * hydro.diffusivity_m2_s * dt_s))
        velocity += rng.normal(0.0, sigma / max(dt_s, 1e-9), size=velocity.shape)

    if hydro.robot_repulsion_enabled and robot_pos is not None:
        rel = field.positions[alive] - robot_pos
        dist = np.linalg.norm(rel, axis=1)
        mask = (dist > 1e-9) & (dist < hydro.robot_repulsion_radius_m)
        if np.any(mask):
            strength = hydro.robot_repulsion_gain_mps * (1.0 - dist[mask] / hydro.robot_repulsion_radius_m) ** 2
            velocity[mask] += rel[mask] / dist[mask, None] * strength[:, None]
            field.pushed_events[alive[mask]] += 1

    field.positions[alive] = reflect_bounds(field.positions[alive] + velocity * dt_s, world)
