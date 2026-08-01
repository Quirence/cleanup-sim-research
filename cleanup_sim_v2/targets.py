from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .config import PlannerConfig, WorldConfig
from .sensors import Detection


@dataclass
class TargetTrack:
    position: np.ndarray
    confidence: float
    hits: int
    first_seen_s: float
    last_seen_s: float
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

    def add_detections(self, detections: list[Detection], t_s: float, world: WorldConfig) -> list[TargetTrack]:
        self.prune(t_s)
        newly_confirmed: list[TargetTrack] = []
        for det in detections:
            if det.confidence < self.planner.target_confirm_confidence:
                continue
            position = np.clip(det.position.astype(float), [0.0, 0.0], [world.width_m, world.height_m])
            if self._is_suppressed(position, t_s):
                continue
            match = self._find_match(position)
            if match is None:
                track = TargetTrack(
                    position=position,
                    confidence=det.confidence,
                    hits=1,
                    first_seen_s=t_s,
                    last_seen_s=t_s,
                    sensors={det.sensor},
                    source_ids=set(),
                )
                self.tracks.append(track)
            else:
                track = match
                track.position = (track.position * track.hits + position) / (track.hits + 1)
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
