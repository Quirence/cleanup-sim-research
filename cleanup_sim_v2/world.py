from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import WorldConfig


@dataclass
class DebrisField:
    positions: np.ndarray
    initial_positions: np.ndarray
    masses_kg: np.ndarray
    sizes_m: np.ndarray
    types: np.ndarray
    collected: np.ndarray
    missed_attempts: np.ndarray
    pushed_events: np.ndarray

    def alive_mask(self) -> np.ndarray:
        return ~self.collected

    def alive_positions(self) -> np.ndarray:
        return self.positions[self.alive_mask()]


def make_debris_field(rng: np.random.Generator, cfg: WorldConfig) -> DebrisField:
    debris_types = np.array(["plastic", "organic", "metal"])
    type_probs = np.array([0.66, 0.26, 0.08])
    mass_mean = {"plastic": 0.28, "organic": 0.45, "metal": 0.65}
    mass_std = {"plastic": 0.12, "organic": 0.18, "metal": 0.20}
    size_mean = {"plastic": 0.20, "organic": 0.16, "metal": 0.12}
    size_std = {"plastic": 0.08, "organic": 0.06, "metal": 0.05}

    if cfg.distribution == "uniform":
        positions = rng.uniform([0.0, 0.0], [cfg.width_m, cfg.height_m], size=(cfg.n_debris, 2))
    else:
        centers = rng.uniform(
            [25.0, 20.0],
            [cfg.width_m - 15.0, cfg.height_m - 20.0],
            size=(cfg.n_clusters, 2),
        )
        sigmas = rng.uniform(cfg.cluster_sigma_min_m, cfg.cluster_sigma_max_m, size=cfg.n_clusters)
        points = []
        for _ in range(cfg.n_debris):
            center_id = int(rng.integers(0, cfg.n_clusters))
            center = centers[center_id]
            sigma = sigmas[center_id]
            p = center.copy()
            for _ in range(32):
                p = rng.normal(center, sigma, size=2)
                if 0.0 <= p[0] <= cfg.width_m and 0.0 <= p[1] <= cfg.height_m:
                    break
            points.append(np.clip(p, [0.0, 0.0], [cfg.width_m, cfg.height_m]))
        positions = np.asarray(points, dtype=float)

    sampled_types = rng.choice(debris_types, p=type_probs, size=cfg.n_debris)
    masses = np.array([
        max(0.03, rng.normal(mass_mean[t], mass_std[t]))
        for t in sampled_types
    ])
    sizes = np.array([
        max(0.04, rng.normal(size_mean[t], size_std[t]))
        for t in sampled_types
    ])
    return DebrisField(
        positions=positions.copy(),
        initial_positions=positions.copy(),
        masses_kg=masses,
        sizes_m=sizes,
        types=sampled_types,
        collected=np.zeros(cfg.n_debris, dtype=bool),
        missed_attempts=np.zeros(cfg.n_debris, dtype=int),
        pushed_events=np.zeros(cfg.n_debris, dtype=int),
    )


def reflect_bounds(positions: np.ndarray, cfg: WorldConfig) -> np.ndarray:
    out = positions.copy()
    out[:, 0] = np.where(out[:, 0] < 0.0, -out[:, 0], out[:, 0])
    out[:, 1] = np.where(out[:, 1] < 0.0, -out[:, 1], out[:, 1])
    out[:, 0] = np.where(out[:, 0] > cfg.width_m, 2.0 * cfg.width_m - out[:, 0], out[:, 0])
    out[:, 1] = np.where(out[:, 1] > cfg.height_m, 2.0 * cfg.height_m - out[:, 1], out[:, 1])
    out[:, 0] = np.clip(out[:, 0], 0.0, cfg.width_m)
    out[:, 1] = np.clip(out[:, 1], 0.0, cfg.height_m)
    return out


def true_count_map(field: DebrisField, x_edges: np.ndarray, y_edges: np.ndarray, include_collected: bool = False) -> np.ndarray:
    counts = np.zeros((len(y_edges) - 1, len(x_edges) - 1), dtype=int)
    indices = np.arange(len(field.positions)) if include_collected else np.where(~field.collected)[0]
    if indices.size == 0:
        return counts
    p = field.positions[indices]
    ix = np.clip(np.searchsorted(x_edges, p[:, 0], side="right") - 1, 0, counts.shape[1] - 1)
    iy = np.clip(np.searchsorted(y_edges, p[:, 1], side="right") - 1, 0, counts.shape[0] - 1)
    np.add.at(counts, (iy, ix), 1)
    return counts
