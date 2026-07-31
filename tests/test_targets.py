from __future__ import annotations

import numpy as np

from cleanup_sim.config import WorldConfig
from cleanup_sim.sensors import Detection
from cleanup_sim.targets import TargetQueue


def test_target_queue_confirms_only_after_enough_hits() -> None:
    queue = TargetQueue(confirm_prob=0.7, confirm_hits=2, nms_radius_m=5.0)
    det = Detection(sensor="camera", position=np.array([20.0, 30.0]), confidence=0.8, source_index=99)

    queue.add_detections([det], t=0.0, world=WorldConfig())
    assert queue.confirmed_targets() == []

    queue.add_detections([det], t=10.0, world=WorldConfig())
    confirmed = queue.confirmed_targets()
    assert len(confirmed) == 1
    assert np.allclose(confirmed[0], [20.0, 30.0], atol=1.0)


def test_target_queue_merges_nearby_detections_and_ignores_source_id() -> None:
    queue = TargetQueue(confirm_prob=0.7, confirm_hits=1, nms_radius_m=6.0)
    detections = [
        Detection(sensor="radar", position=np.array([50.0, 50.0]), confidence=0.76, source_index=1),
        Detection(sensor="camera", position=np.array([53.0, 51.0]), confidence=0.88, source_index=1),
    ]

    queue.add_detections(detections, t=0.0, world=WorldConfig())

    assert len(queue.tracks) == 1
    assert queue.tracks[0].source_ids == set()
    assert queue.tracks[0].confidence >= 0.88


def test_target_queue_removes_targets_near_robot() -> None:
    queue = TargetQueue(confirm_prob=0.7, confirm_hits=1, nms_radius_m=5.0)
    queue.add_detections(
        [Detection(sensor="camera", position=np.array([10.0, 10.0]), confidence=0.9, source_index=None)],
        t=0.0,
        world=WorldConfig(),
    )

    removed = queue.remove_near(np.array([11.0, 10.0]), radius_m=2.0)

    assert removed == 1
    assert queue.confirmed_targets() == []


def test_target_queue_reports_new_confirmations_once() -> None:
    queue = TargetQueue(confirm_prob=0.7, confirm_hits=2, nms_radius_m=5.0)
    det = Detection(sensor="camera", position=np.array([20.0, 30.0]), confidence=0.8, source_index=None)

    assert queue.add_detections([det], t=0.0, world=WorldConfig()) == []
    confirmations = queue.add_detections([det], t=1.0, world=WorldConfig())
    repeated = queue.add_detections([det], t=2.0, world=WorldConfig())

    assert len(confirmations) == 1
    assert np.allclose(confirmations[0].position, [20.0, 30.0], atol=1.0)
    assert repeated == []


def test_target_queue_suppresses_false_visit_region() -> None:
    queue = TargetQueue(confirm_prob=0.7, confirm_hits=1, nms_radius_m=5.0)
    world = WorldConfig()
    queue.add_detections(
        [Detection(sensor="radar", position=np.array([40.0, 40.0]), confidence=0.9, source_index=None)],
        t=0.0,
        world=world,
    )
    removed = queue.suppress_near(np.array([40.0, 40.0]), radius_m=12.0)
    queue.add_detections(
        [Detection(sensor="radar", position=np.array([42.0, 39.0]), confidence=0.95, source_index=None)],
        t=10.0,
        world=world,
    )

    assert removed == 1
    assert queue.confirmed_targets() == []
