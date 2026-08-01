from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import PlatformConfig
from .world import DebrisField


@dataclass(frozen=True)
class CaptureEvent:
    debris_id: int
    success: bool
    position: np.ndarray
    mass_kg: float
    reason: str


def _heading_vector(prev_pos: np.ndarray, new_pos: np.ndarray, heading_rad: float) -> np.ndarray:
    delta = new_pos - prev_pos
    dist = float(np.linalg.norm(delta))
    if dist > 1e-9:
        return delta / dist
    return np.array([np.cos(heading_rad), np.sin(heading_rad)], dtype=float)


def aperture_candidates(
    field: DebrisField,
    prev_pos: np.ndarray,
    new_pos: np.ndarray,
    heading_rad: float,
    platform: PlatformConfig,
) -> np.ndarray:
    alive = np.where(~field.collected)[0]
    if alive.size == 0:
        return alive
    direction = _heading_vector(prev_pos, new_pos, heading_rad)
    rel = field.positions[alive] - prev_pos
    along = rel @ direction
    lateral = np.abs(rel[:, 0] * direction[1] - rel[:, 1] * direction[0])
    swept_len = float(np.linalg.norm(new_pos - prev_pos)) + platform.collection_length_m
    mask = (
        (along >= -0.15 * platform.collection_length_m)
        & (along <= swept_len)
        & (lateral <= 0.5 * platform.collection_width_m)
    )
    candidates = alive[mask]
    if candidates.size <= 1:
        return candidates
    order = np.argsort(along[mask])
    return candidates[order]


def collect_in_aperture(
    rng: np.random.Generator,
    field: DebrisField,
    prev_pos: np.ndarray,
    new_pos: np.ndarray,
    heading_rad: float,
    platform: PlatformConfig,
    bin_load_kg: float,
    dt_s: float,
) -> tuple[list[CaptureEvent], float]:
    remaining_capacity = max(0.0, platform.bin_capacity_kg - bin_load_kg)
    throughput_budget = max(0.0, platform.collection_throughput_kg_s * dt_s)
    mass_budget = min(remaining_capacity, throughput_budget)
    events: list[CaptureEvent] = []

    for debris_id in aperture_candidates(field, prev_pos, new_pos, heading_rad, platform):
        mass = float(field.masses_kg[debris_id])
        pos = field.positions[debris_id].copy()
        if mass > remaining_capacity:
            events.append(CaptureEvent(int(debris_id), False, pos, mass, "bin_full"))
            continue
        if mass > mass_budget + 1e-9:
            events.append(CaptureEvent(int(debris_id), False, pos, mass, "throughput_limit"))
            continue
        if rng.random() <= platform.capture_probability:
            field.collected[debris_id] = True
            bin_load_kg += mass
            remaining_capacity -= mass
            mass_budget -= mass
            events.append(CaptureEvent(int(debris_id), True, pos, mass, "captured"))
        else:
            field.missed_attempts[debris_id] += 1
            events.append(CaptureEvent(int(debris_id), False, pos, mass, "missed_capture"))
    return events, bin_load_kg
