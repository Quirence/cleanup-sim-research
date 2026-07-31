from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import WorldConfig


@dataclass
class DebrisField:
    positions: np.ndarray
    masses: np.ndarray
    types: np.ndarray
    collected: np.ndarray


def make_debris_field(rng: np.random.Generator, cfg: WorldConfig) -> DebrisField:
    types = np.array(["plastic", "organic", "metal"])
    type_probs = np.array([0.6, 0.3, 0.1])
    mass_mean = {"plastic": 0.4, "organic": 0.6, "metal": 0.8}
    mass_std = {"plastic": 0.15, "organic": 0.2, "metal": 0.25}

    if cfg.distribution == "uniform":
        positions = rng.uniform([0.0, 0.0], [cfg.width, cfg.height], size=(cfg.n_debris, 2))
    else:
        centers = rng.uniform([30.0, 20.0], [cfg.width - 10.0, cfg.height - 20.0], size=(cfg.n_clusters, 2))
        sigmas = rng.uniform(cfg.cluster_sigma_min, cfg.cluster_sigma_max, size=cfg.n_clusters)
        pts = []
        for _ in range(cfg.n_debris):
            center_id = int(rng.integers(0, cfg.n_clusters))
            center = centers[center_id]
            sigma = sigmas[center_id]
            for _ in range(24):
                p = rng.normal(center, sigma, size=2)
                if 0.0 <= p[0] <= cfg.width and 0.0 <= p[1] <= cfg.height:
                    break
            pts.append(np.clip(p, [0.0, 0.0], [cfg.width, cfg.height]))
        positions = np.asarray(pts, dtype=float)

    sampled_types = rng.choice(types, p=type_probs, size=cfg.n_debris)
    masses = np.array([
        max(0.05, rng.normal(mass_mean[t], mass_std[t]))
        for t in sampled_types
    ])
    return DebrisField(
        positions=positions,
        masses=masses,
        types=sampled_types,
        collected=np.zeros(cfg.n_debris, dtype=bool),
    )


def true_occupancy(
    field: DebrisField,
    x_edges: np.ndarray,
    y_edges: np.ndarray,
    include_collected: bool = True,
) -> np.ndarray:
    occ = np.zeros((len(y_edges) - 1, len(x_edges) - 1), dtype=bool)
    indices = np.arange(len(field.positions)) if include_collected else np.where(~field.collected)[0]
    if indices.size == 0:
        return occ
    positions = field.positions[indices]
    ix = np.clip(np.searchsorted(x_edges, positions[:, 0], side="right") - 1, 0, occ.shape[1] - 1)
    iy = np.clip(np.searchsorted(y_edges, positions[:, 1], side="right") - 1, 0, occ.shape[0] - 1)
    occ[iy, ix] = True
    return occ
