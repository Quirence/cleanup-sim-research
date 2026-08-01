from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from .config import PlatformConfig
from .world import DebrisField


@dataclass(frozen=True)
class CaptureEvent:
    debris_id: int
    success: bool
    position: np.ndarray
    mass_kg: float
    reason: str
    work_kg: float = 0.0
    required_work_kg: float = 0.0
    terminal: bool = False


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
    path_len = float(np.linalg.norm(new_pos - prev_pos))
    mid = 0.5 * (prev_pos + new_pos)
    prefilter_radius = 0.5 * path_len + platform.collection_length_m + 0.5 * platform.collection_width_m
    local_ids = np.asarray(cKDTree(field.positions[alive]).query_ball_point(mid, prefilter_radius), dtype=int)
    if local_ids.size == 0:
        return np.asarray([], dtype=int)
    alive = alive[local_ids]
    rel = field.positions[alive] - prev_pos
    along = rel @ direction
    lateral = np.abs(rel[:, 0] * direction[1] - rel[:, 1] * direction[0])
    swept_len = path_len + platform.collection_length_m
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
    speed_mps: float | None = None,
) -> tuple[list[CaptureEvent], float]:
    remaining_capacity = max(0.0, platform.bin_capacity_kg - bin_load_kg)
    if speed_mps is None or speed_mps <= platform.collection_speed_mps + 1e-9:
        speed_efficiency = 1.0
    else:
        speed_efficiency = max(0.15, platform.collection_speed_mps / max(speed_mps, 1e-9))
    throughput_budget = max(0.0, platform.collection_throughput_kg_s * dt_s * speed_efficiency)
    mass_budget = min(remaining_capacity, throughput_budget)
    events: list[CaptureEvent] = []

    for debris_id in aperture_candidates(field, prev_pos, new_pos, heading_rad, platform):
        mass = float(field.masses_kg[debris_id])
        pos = field.positions[debris_id].copy()
        required_work = max(mass, platform.collection_throughput_kg_s * platform.capture_time_s)
        if mass > remaining_capacity:
            events.append(CaptureEvent(int(debris_id), False, pos, mass, "bin_full", 0.0, required_work, True))
            continue

        needed_work = max(0.0, required_work - float(field.capture_progress_kg[debris_id]))
        allocated_work = min(mass_budget, needed_work)
        if allocated_work <= 1e-12:
            events.append(
                CaptureEvent(
                    int(debris_id),
                    False,
                    pos,
                    mass,
                    "throughput_limit",
                    float(field.capture_progress_kg[debris_id]),
                    required_work,
                    False,
                )
            )
            continue
        field.capture_progress_kg[debris_id] += allocated_work
        mass_budget -= allocated_work

        if field.capture_progress_kg[debris_id] + 1e-9 < required_work:
            events.append(
                CaptureEvent(
                    int(debris_id),
                    False,
                    pos,
                    mass,
                    "partial_contact",
                    float(field.capture_progress_kg[debris_id]),
                    required_work,
                    False,
                )
            )
            continue

        if rng.random() <= platform.capture_probability:
            field.collected[debris_id] = True
            field.capture_progress_kg[debris_id] = 0.0
            bin_load_kg += mass
            remaining_capacity -= mass
            events.append(CaptureEvent(int(debris_id), True, pos, mass, "captured", required_work, required_work, True))
        else:
            field.missed_attempts[debris_id] += 1
            field.capture_progress_kg[debris_id] = 0.0
            events.append(
                CaptureEvent(int(debris_id), False, pos, mass, "missed_capture", required_work, required_work, True)
            )
    return events, bin_load_kg
