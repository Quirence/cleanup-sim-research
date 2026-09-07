from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .config import HydroConfig, PlannerConfig, WorldConfig
from .hydrodynamics import ambient_velocity
from .sensors import Detection


@dataclass
class TargetTrack:
    track_id: int
    position: np.ndarray
    confidence: float
    hits: int
    first_seen_s: float
    last_seen_s: float
    localization_sigma_m: float = 0.0
    sensors: set[str] = field(default_factory=set)
    source_ids: set[int] = field(default_factory=set)
    reported_confirmed: bool = False
    empty_visits: int = 0

    def confirmed(self, planner: PlannerConfig) -> bool:
        return (
            self.confidence >= planner.target_confirm_confidence
            and self.hits >= planner.target_confirm_hits
            and len(self.sensors) >= planner.target_min_sensor_types
        )


class TargetQueue:
    def __init__(self, planner: PlannerConfig) -> None:
        self.planner = planner
        self.tracks: list[TargetTrack] = []
        self.suppressed_regions: list[tuple[np.ndarray, float]] = []
        self._next_track_id = 1

    def add_detections(self, detections: list[Detection], t_s: float, world: WorldConfig) -> list[TargetTrack]:
        self.prune(t_s)
        newly_confirmed: list[TargetTrack] = []
        for det in detections:
            if det.confidence < self.planner.target_confirm_confidence:
                continue
            position = np.clip(det.position.astype(float), [0.0, 0.0], [world.width_m, world.height_m])
            if self._is_suppressed(position, t_s):
                continue
            det_sigma = max(float(det.localization_sigma_m), 0.5)
            match = self._find_match(position)
            if match is None:
                track = TargetTrack(
                    track_id=self._next_track_id,
                    position=position,
                    confidence=det.confidence,
                    hits=1,
                    first_seen_s=t_s,
                    last_seen_s=t_s,
                    localization_sigma_m=det_sigma,
                    sensors={det.sensor},
                    source_ids=set(),
                )
                self._next_track_id += 1
                self.tracks.append(track)
            else:
                track = match
                track_sigma = max(float(track.localization_sigma_m), 0.5)
                track_weight = 1.0 / (track_sigma * track_sigma)
                det_weight = 1.0 / (det_sigma * det_sigma)
                track.position = (track.position * track_weight + position * det_weight) / (track_weight + det_weight)
                track.localization_sigma_m = float(np.sqrt(1.0 / (track_weight + det_weight)))
                track.confidence = max(track.confidence, det.confidence)
                track.hits += 1
                track.last_seen_s = t_s
                track.sensors.add(det.sensor)
            if track.confirmed(self.planner) and not track.reported_confirmed:
                track.reported_confirmed = True
                newly_confirmed.append(track)
        return newly_confirmed

    def confirmed_targets(self, t_s: float | None = None) -> list[np.ndarray]:
        if t_s is not None:
            self.prune(t_s)
        return [track.position.copy() for track in self.tracks if track.confirmed(self.planner)]

    def predict(self, hydro: HydroConfig, world: WorldConfig, dt_s: float) -> None:
        velocity = ambient_velocity(hydro)
        diffusion_sigma = float(np.sqrt(max(0.0, 2.0 * hydro.diffusivity_m2_s * dt_s)))
        for track in self.tracks:
            track.position = np.clip(track.position + velocity * dt_s, [0.0, 0.0], [world.width_m, world.height_m])
            if diffusion_sigma > 0.0:
                track.localization_sigma_m = float(np.hypot(track.localization_sigma_m, diffusion_sigma))

    def remove_near(self, position: np.ndarray, radius_m: float) -> int:
        before = len(self.tracks)
        self.tracks = [t for t in self.tracks if np.linalg.norm(t.position - position) > radius_m]
        return before - len(self.tracks)

    def suppress_near(self, position: np.ndarray, t_s: float, radius_m: float | None = None) -> int:
        radius = self.planner.target_suppression_radius_m if radius_m is None else radius_m
        removed = self.remove_near(position, radius)
        self.suppressed_regions.append((position.astype(float).copy(), t_s + self.planner.target_stale_after_s))
        return removed

    def prune(self, t_s: float) -> None:
        self.tracks = [
            track
            for track in self.tracks
            if t_s - track.last_seen_s <= self.planner.target_stale_after_s
        ]
        self.suppressed_regions = [
            (position, until_s)
            for position, until_s in self.suppressed_regions
            if until_s >= t_s
        ]

    def _find_match(self, position: np.ndarray) -> TargetTrack | None:
        for track in self.tracks:
            if np.linalg.norm(track.position - position) <= self.planner.target_nms_radius_m:
                return track
        return None

    def _is_suppressed(self, position: np.ndarray, t_s: float) -> bool:
        for center, until_s in self.suppressed_regions:
            if until_s >= t_s and np.linalg.norm(position - center) <= self.planner.target_suppression_radius_m:
                return True
        return False
