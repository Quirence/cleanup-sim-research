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

    def add_detections(self, detections: list[Detection], t_s: float, world: WorldConfig) -> list[TargetTrack]:
        newly_confirmed: list[TargetTrack] = []
        for det in detections:
            if det.confidence < self.planner.target_confirm_confidence:
                continue
            position = np.clip(det.position.astype(float), [0.0, 0.0], [world.width_m, world.height_m])
            match = self._find_match(position)
            if match is None:
                track = TargetTrack(
                    position=position,
                    confidence=det.confidence,
                    hits=1,
                    first_seen_s=t_s,
                    last_seen_s=t_s,
                    sensors={det.sensor},
                    source_ids=set() if det.source_index is None else {int(det.source_index)},
                )
                self.tracks.append(track)
            else:
                track = match
                track.position = (track.position * track.hits + position) / (track.hits + 1)
                track.confidence = max(track.confidence, det.confidence)
                track.hits += 1
                track.last_seen_s = t_s
                track.sensors.add(det.sensor)
                if det.source_index is not None:
                    track.source_ids.add(int(det.source_index))
            if track.confirmed(self.planner) and not track.reported_confirmed:
                track.reported_confirmed = True
                newly_confirmed.append(track)
        return newly_confirmed

    def confirmed_targets(self) -> list[np.ndarray]:
        return [track.position.copy() for track in self.tracks if track.confirmed(self.planner)]

    def remove_near(self, position: np.ndarray, radius_m: float) -> int:
        before = len(self.tracks)
        self.tracks = [t for t in self.tracks if np.linalg.norm(t.position - position) > radius_m]
        return before - len(self.tracks)

    def _find_match(self, position: np.ndarray) -> TargetTrack | None:
        for track in self.tracks:
            if np.linalg.norm(track.position - position) <= self.planner.target_nms_radius_m:
                return track
        return None
