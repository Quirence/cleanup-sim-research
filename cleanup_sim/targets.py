from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .config import WorldConfig
from .sensors import Detection


@dataclass
class TargetTrack:
    position: np.ndarray
    confidence: float
    hits: int
    first_seen_s: float
    last_seen_s: float
    source_ids: set[int] = field(default_factory=set)
    reported_confirmed: bool = False

    def confirmed_by(self, confirm_prob: float, confirm_hits: int) -> bool:
        return self.confidence >= confirm_prob and self.hits >= confirm_hits


class TargetQueue:
    def __init__(self, confirm_prob: float, confirm_hits: int, nms_radius_m: float) -> None:
        self.confirm_prob = confirm_prob
        self.confirm_hits = confirm_hits
        self.nms_radius_m = nms_radius_m
        self.tracks: list[TargetTrack] = []
        self.suppressed_regions: list[tuple[np.ndarray, float]] = []

    def add_detections(self, detections: list[Detection], t: float, world: WorldConfig) -> list[TargetTrack]:
        newly_confirmed: list[TargetTrack] = []
        for det in detections:
            if det.confidence < self.confirm_prob:
                continue
            position = np.clip(det.position.astype(float), [0.0, 0.0], [world.width, world.height])
            if self._is_suppressed(position):
                continue
            match = self._find_match(position)
            if match is None:
                self.tracks.append(
                    TargetTrack(
                        position=position,
                        confidence=det.confidence,
                        hits=1,
                        first_seen_s=t,
                        last_seen_s=t,
                    )
                )
            else:
                total_hits = match.hits + 1
                match.position = (match.position * match.hits + position) / total_hits
                match.confidence = max(match.confidence, det.confidence)
                match.hits = total_hits
                match.last_seen_s = t
            track = match if match is not None else self.tracks[-1]
            if track.confirmed_by(self.confirm_prob, self.confirm_hits) and not track.reported_confirmed:
                track.reported_confirmed = True
                newly_confirmed.append(track)
        return newly_confirmed

    def confirmed_targets(self) -> list[np.ndarray]:
        return [
            track.position.copy()
            for track in self.tracks
            if track.confirmed_by(self.confirm_prob, self.confirm_hits)
        ]

    def remove_near(self, position: np.ndarray, radius_m: float) -> int:
        before = len(self.tracks)
        self.tracks = [
            track
            for track in self.tracks
            if np.linalg.norm(track.position - position) > radius_m
        ]
        return before - len(self.tracks)

    def suppress_near(self, position: np.ndarray, radius_m: float) -> int:
        removed = self.remove_near(position, radius_m)
        self.suppressed_regions.append((position.astype(float).copy(), float(radius_m)))
        return removed

    def expire_stale(self, t: float, stale_after_s: float) -> int:
        before = len(self.tracks)
        self.tracks = [
            track
            for track in self.tracks
            if t - track.last_seen_s <= stale_after_s
        ]
        return before - len(self.tracks)

    def _find_match(self, position: np.ndarray) -> TargetTrack | None:
        for track in self.tracks:
            if np.linalg.norm(track.position - position) <= self.nms_radius_m:
                return track
        return None

    def _is_suppressed(self, position: np.ndarray) -> bool:
        return any(np.linalg.norm(position - center) <= radius for center, radius in self.suppressed_regions)
