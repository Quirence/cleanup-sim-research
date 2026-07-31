from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import GridConfig, WorldConfig


EPS = 1e-9


@dataclass
class Grid:
    x_edges: np.ndarray
    y_edges: np.ndarray
    x_centers: np.ndarray
    y_centers: np.ndarray
    xx: np.ndarray
    yy: np.ndarray


@dataclass
class ProbabilityMap:
    grid: Grid
    belief: np.ndarray
    prior: float

    def copy(self) -> "ProbabilityMap":
        return ProbabilityMap(self.grid, self.belief.copy(), self.prior)


def make_grid(world: WorldConfig, grid_cfg: GridConfig) -> Grid:
    x_edges = np.linspace(0.0, world.width, grid_cfg.nx + 1)
    y_edges = np.linspace(0.0, world.height, grid_cfg.ny + 1)
    x_centers = 0.5 * (x_edges[:-1] + x_edges[1:])
    y_centers = 0.5 * (y_edges[:-1] + y_edges[1:])
    xx, yy = np.meshgrid(x_centers, y_centers, indexing="xy")
    return Grid(x_edges, y_edges, x_centers, y_centers, xx, yy)


def init_probability_map(grid: Grid, cfg: GridConfig) -> ProbabilityMap:
    return ProbabilityMap(grid=grid, belief=np.full(grid.xx.shape, cfg.prior, dtype=float), prior=cfg.prior)


def entropy(belief: np.ndarray) -> np.ndarray:
    b = np.clip(belief, EPS, 1.0 - EPS)
    return -(b * np.log(b) + (1.0 - b) * np.log(1.0 - b))


def bayesian_update(prior: np.ndarray, z: np.ndarray, p_z1_occ: np.ndarray, p_z1_free: np.ndarray) -> np.ndarray:
    prior = np.clip(prior, EPS, 1.0 - EPS)
    p_z_occ = np.where(z, p_z1_occ, 1.0 - p_z1_occ)
    p_z_free = np.where(z, p_z1_free, 1.0 - p_z1_free)
    numerator = p_z_occ * prior
    denominator = numerator + p_z_free * (1.0 - prior)
    return np.clip(numerator / np.clip(denominator, EPS, None), EPS, 1.0 - EPS)


def cell_indices_for_points(grid: Grid, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    ix = np.clip(np.searchsorted(grid.x_edges, points[:, 0], side="right") - 1, 0, len(grid.x_centers) - 1)
    iy = np.clip(np.searchsorted(grid.y_edges, points[:, 1], side="right") - 1, 0, len(grid.y_centers) - 1)
    return iy, ix
