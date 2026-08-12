from __future__ import annotations

import numpy as np

from cleanup_sim_v2.config import SensorConfig, SensorSuiteConfig, WorldConfig
from cleanup_sim_v2.sensors import (
    detect_with_sensor,
    detect_with_suite,
    detection_probability,
    in_sensor_fov,
    wrap_angle,
)
from cleanup_sim_v2.world import DebrisField


def _sensor(**overrides) -> SensorConfig:
    base = dict(
        name="camera",
        range_m=20.0,
        fov_deg=90.0,
        p_detect_max=1.0,
        decay_range_m=1e9,
        min_detectable_size_m=0.2,
        localization_sigma_m=0.0,
        localization_sigma_per_m=0.0,
        clutter_rate_per_m2=0.0,
        confidence_sigma=0.0,
    )
    base.update(overrides)
    return SensorConfig(**base)


def _field_at(points: list[tuple[float, float]], sizes_m: float = 0.2) -> DebrisField:
    positions = np.array(points, dtype=float)
    n = len(points)
    return DebrisField(
        positions=positions.copy(),
        initial_positions=positions.copy(),
        masses_kg=np.full(n, 0.2),
        sizes_m=np.full(n, sizes_m),
        types=np.array(["plastic"] * n),
        collected=np.zeros(n, dtype=bool),
        missed_attempts=np.zeros(n, dtype=int),
        pushed_events=np.zeros(n, dtype=int),
        capture_progress_kg=np.zeros(n, dtype=float),
    )


def test_wrap_angle_keeps_values_in_canonical_range() -> None:
    for angle in [0.0, 0.1, -0.1, np.pi - 0.01, -(np.pi - 0.01)]:
        wrapped = wrap_angle(angle)
        assert -np.pi <= wrapped <= np.pi
        assert np.isclose(wrapped, angle)


def test_wrap_angle_handles_the_plus_minus_180_degree_boundary() -> None:
    # Exactly at +/-pi both map to -pi (the formula's chosen canonical boundary).
    assert np.isclose(wrap_angle(np.pi), -np.pi)
    assert np.isclose(wrap_angle(-np.pi), -np.pi)
    # Angles that cross the boundary by wrapping multiple full turns must reduce to
    # the same value modulo 2*pi.
    assert np.isclose(wrap_angle(2 * np.pi + 0.3), 0.3)
    assert np.isclose(wrap_angle(-2 * np.pi - 0.3), -0.3)
    # Just past +pi wraps around to just past -pi, not to a value near 0.
    assert np.isclose(wrap_angle(np.pi + 0.05), -np.pi + 0.05)


def test_in_sensor_fov_respects_range_and_field_of_view() -> None:
    sensor = _sensor(range_m=10.0, fov_deg=90.0)
    pose = np.array([0.0, 0.0, 0.0])
    points = np.array([
        [5.0, 0.0],    # in range, dead ahead -> visible
        [15.0, 0.0],   # out of range, dead ahead -> not visible
        [5.0, 5.0],    # in range, 45 degrees off-axis (exactly at the FOV edge) -> visible
        [-5.0, 0.0],   # in range, 180 degrees off-axis (directly behind) -> not visible
    ])

    mask, distance, bearing = in_sensor_fov(points, pose, sensor)

    assert mask.tolist() == [True, False, True, False]
    assert np.allclose(distance, [5.0, 15.0, np.hypot(5.0, 5.0), 5.0])
    assert np.isclose(bearing[0], 0.0)


def test_in_sensor_fov_bearing_is_relative_to_pose_heading() -> None:
    sensor = _sensor(range_m=10.0, fov_deg=10.0)
    point_dead_ahead_of_heading = np.array([[1.0, 1.0]])
    # Heading pi/4 points directly at (1, 1) from the origin, so a narrow 10-degree
    # FOV should still see it.
    pose = np.array([0.0, 0.0, np.pi / 4])

    mask, _, bearing = in_sensor_fov(point_dead_ahead_of_heading, pose, sensor)

    assert mask[0]
    assert np.isclose(bearing[0], 0.0, atol=1e-9)


def test_detection_probability_decreases_with_distance() -> None:
    sensor = _sensor(decay_range_m=10.0)
    near = detection_probability(sensor, np.array([1.0]), np.array([0.5]))
    far = detection_probability(sensor, np.array([50.0]), np.array([0.5]))
    assert near[0] > far[0]


def test_detection_probability_increases_with_object_size_up_to_a_cap() -> None:
    # Use a moderate p_detect_max so the size scaling isn't immediately saturated
    # by the 0.98 output clip.
    sensor = _sensor(min_detectable_size_m=0.2, p_detect_max=0.5)
    tiny = detection_probability(sensor, np.array([1.0]), np.array([0.01]))
    normal = detection_probability(sensor, np.array([1.0]), np.array([0.2]))
    huge = detection_probability(sensor, np.array([1.0]), np.array([50.0]))
    assert tiny[0] < normal[0] < huge[0]
    assert huge[0] <= 0.98


def test_detect_with_sensor_finds_a_visible_object_deterministically() -> None:
    rng = np.random.default_rng(0)
    field = _field_at([(5.0, 0.0)])
    sensor = _sensor(p_detect_max=1.0, range_m=20.0, fov_deg=180.0)
    pose = np.array([0.0, 0.0, 0.0])

    detections = detect_with_sensor(rng, field, WorldConfig(), pose, sensor)

    assert len(detections) == 1
    assert detections[0].is_false is False
    assert detections[0].source_index == 0
    assert detections[0].sensor == "camera"


def test_detect_with_sensor_ignores_already_collected_debris() -> None:
    rng = np.random.default_rng(0)
    field = _field_at([(5.0, 0.0)])
    field.collected[0] = True
    sensor = _sensor(p_detect_max=1.0, range_m=20.0, fov_deg=180.0, clutter_rate_per_m2=0.0)
    pose = np.array([0.0, 0.0, 0.0])

    detections = detect_with_sensor(rng, field, WorldConfig(), pose, sensor)

    assert detections == []


def test_detect_with_sensor_ignores_debris_outside_fov() -> None:
    rng = np.random.default_rng(0)
    field = _field_at([(-5.0, 0.0)])  # directly behind a forward-facing sensor
    sensor = _sensor(p_detect_max=1.0, range_m=20.0, fov_deg=90.0, clutter_rate_per_m2=0.0)
    pose = np.array([0.0, 0.0, 0.0])

    detections = detect_with_sensor(rng, field, WorldConfig(), pose, sensor)

    assert detections == []


def test_detect_with_suite_aggregates_detections_from_every_sensor() -> None:
    rng = np.random.default_rng(0)
    field = _field_at([(5.0, 0.0)])
    suite = SensorSuiteConfig(
        camera=_sensor(name="camera", p_detect_max=1.0, range_m=20.0, fov_deg=180.0),
        radar=_sensor(name="radar", p_detect_max=1.0, range_m=20.0, fov_deg=180.0),
    )
    pose = np.array([0.0, 0.0, 0.0])

    detections = detect_with_suite(rng, field, WorldConfig(), pose, suite)

    sensors_seen = {det.sensor for det in detections}
    assert sensors_seen == {"camera", "radar"}
