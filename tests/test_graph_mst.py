from __future__ import annotations

import numpy as np

from cleanup_sim.planners import mst_route


def test_mst_route_visits_each_target_exactly_once() -> None:
    start = np.array([0.0, 0.0])
    targets = [np.array([10.0, 0.0]), np.array([0.0, 10.0]), np.array([10.0, 10.0])]

    route = mst_route(start, targets)

    assert len(route) == len(targets)
    visited = {tuple(np.round(p, 6)) for p in route}
    expected = {tuple(np.round(p, 6)) for p in targets}
    assert visited == expected


def test_mst_route_orders_collinear_points_without_backtracking() -> None:
    start = np.array([0.0, 0.0])
    targets = [np.array([30.0, 0.0]), np.array([10.0, 0.0]), np.array([20.0, 0.0])]

    route = mst_route(start, targets)

    assert [float(p[0]) for p in route] == [10.0, 20.0, 30.0]


def test_mst_route_respects_limit() -> None:
    start = np.array([0.0, 0.0])
    targets = [np.array([10.0, 0.0]), np.array([20.0, 0.0]), np.array([30.0, 0.0])]

    route = mst_route(start, targets, limit=2)

    assert len(route) == 2


def test_mst_route_handles_empty_targets() -> None:
    assert mst_route(np.array([0.0, 0.0]), []) == []
