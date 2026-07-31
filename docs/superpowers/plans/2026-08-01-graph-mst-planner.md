# MST Graph Planner (`graph_mst`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new planner mode `graph_mst` that routes to confirmed debris targets by building a minimum-spanning-tree over them (Prim's algorithm) and walking a preorder traversal of that tree, rebuilding the tree whenever a new target is confirmed mid-route, so it can be compared against the existing `nearest_neighbor_route`-based `detected_tsp`/`hybrid` strategies.

**Architecture:** All changes are additive to `cleanup_sim/planners.py` (new `mst_route` + `should_invalidate_graph_route` functions, new `choose_next_goal` branch), `cleanup_sim/config.py` (new `PlannerMode` literal value), `cleanup_sim/simulation.py` (one small hook to invalidate the in-flight route when a new target is confirmed), and the two CLI entry points that gate mode strings via `argparse(choices=...)`. No existing function signatures change; no new `PlannerConfig` fields are added (the mode reuses `detected_confirm_prob`, `target_confirm_hits`, `detected_nms_radius_m`, `target_min_sensor_types`, `detected_batch_size`).

**Tech Stack:** Python 3.11/3.12, numpy, pandas, pytest (existing project stack — see `pyproject.toml`).

## Global Constraints

- Work happens on git branch `dev`; do not merge to `main` as part of this plan.
- Do not modify `cleanup_sim/confirmatory.py` or any file under `docs/article/stage2/` — the frozen paper pipeline/preregistration is out of scope.
- Do not add new `PlannerConfig` fields — reuse `detected_confirm_prob`, `target_confirm_hits`, `detected_nms_radius_m`, `target_min_sensor_types`, `detected_batch_size` (all already defined in `cleanup_sim/config.py`).
- Do not modify `cleanup_sim/hybrid.py` or the `hybrid` mode's explore/route switch — `graph_mst` is a standalone mode.
- Add `graph_mst` to CLI `choices` lists (so it's runnable) but NOT to `DEFAULT_MODES` in `cleanup_sim/run_experiments.py` — it must not appear in default experiment sweeps.
- Match existing code style: `from __future__ import annotations`, dataclasses, type hints, numpy vectorized-where-natural, no comments unless explaining non-obvious behavior (matches current `cleanup_sim/planners.py` style).

---

### Task 1: `mst_route` — MST-based multi-target routing algorithm

**Files:**
- Modify: `cleanup_sim/planners.py` (insert after `nearest_neighbor_route`, which currently ends at line 72, right before `def next_lawnmower`)
- Create: `tests/test_graph_mst.py`

**Interfaces:**
- Produces: `mst_route(start: np.ndarray, targets: list[np.ndarray], limit: int | None = None) -> list[np.ndarray]` — builds a Prim MST over `[start] + targets`, returns a preorder-DFS visiting order of `targets` (excluding `start`), nearest-child-first, truncated to `limit` if given. Consumed by Task 2.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_graph_mst.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_graph_mst.py -v`
Expected: FAIL/ERROR on all four tests with `ImportError: cannot import name 'mst_route' from 'cleanup_sim.planners'`

- [ ] **Step 3: Implement `mst_route`**

In `cleanup_sim/planners.py`, insert this function immediately after `nearest_neighbor_route` (after its closing `return route` at line 72) and before `def next_lawnmower`:

```python
def mst_route(start: np.ndarray, targets: list[np.ndarray], limit: int | None = None) -> list[np.ndarray]:
    if not targets:
        return []
    nodes = [np.asarray(start, dtype=float)] + [np.asarray(t, dtype=float) for t in targets]
    n = len(nodes)
    in_tree = [False] * n
    in_tree[0] = True
    min_edge = [float("inf")] * n
    parent = [0] * n
    for j in range(1, n):
        min_edge[j] = float(np.linalg.norm(nodes[j] - nodes[0]))
    adjacency: dict[int, list[int]] = {i: [] for i in range(n)}
    for _ in range(n - 1):
        u = -1
        best = float("inf")
        for j in range(n):
            if not in_tree[j] and min_edge[j] < best:
                best = min_edge[j]
                u = j
        in_tree[u] = True
        adjacency[parent[u]].append(u)
        adjacency[u].append(parent[u])
        for j in range(n):
            if not in_tree[j]:
                d = float(np.linalg.norm(nodes[j] - nodes[u]))
                if d < min_edge[j]:
                    min_edge[j] = d
                    parent[j] = u
    order: list[int] = []
    visited = [False] * n
    stack = [0]
    while stack:
        node = stack.pop()
        if visited[node]:
            continue
        visited[node] = True
        if node != 0:
            order.append(node)
        children = [j for j in adjacency[node] if not visited[j]]
        children.sort(key=lambda j: float(np.linalg.norm(nodes[j] - nodes[node])), reverse=True)
        stack.extend(children)
    route = [nodes[i] for i in order]
    return route[:limit] if limit is not None else route
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_graph_mst.py -v`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add cleanup_sim/planners.py tests/test_graph_mst.py
git commit -m "Add mst_route: Prim MST + preorder-DFS multi-target routing"
```

---

### Task 2: Wire `graph_mst` into the planner mode dispatch

**Files:**
- Modify: `cleanup_sim/config.py` (`PlannerMode` literal, lines 9-20)
- Modify: `cleanup_sim/planners.py` (`choose_next_goal`, branch to insert after the existing `detected_tsp` branch which currently spans lines 196-202, before the `hybrid` branch at line 203)
- Modify: `tests/test_graph_mst.py`

**Interfaces:**
- Consumes: `mst_route(start, targets, limit)` from Task 1; `TargetQueue.confirmed_targets() -> list[np.ndarray]` and `TargetQueue.add_detections(...)` from `cleanup_sim/targets.py`; `next_lawnmower(state) -> np.ndarray` and `choose_next_goal(...)` already defined in `cleanup_sim/planners.py`.
- Produces: `choose_next_goal(..., planner.mode="graph_mst", ...)` now returns `(goal: np.ndarray, "route")` when confirmed targets exist, `(goal: np.ndarray, "coverage")` otherwise. Consumed by Task 3 (simulation loop) and Task 4 (CLI).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_graph_mst.py` (add these imports at the top alongside the existing ones):

```python
from dataclasses import replace

from cleanup_sim.config import scenario_config
from cleanup_sim.mapping import init_probability_map, make_grid
from cleanup_sim.planners import PlannerState, choose_next_goal, lawnmower_route
from cleanup_sim.sensors import Detection
from cleanup_sim.targets import TargetQueue
```

```python
def _empty_target_queue(cfg) -> TargetQueue:
    return TargetQueue(
        confirm_prob=cfg.planner.detected_confirm_prob,
        confirm_hits=cfg.planner.target_confirm_hits,
        nms_radius_m=cfg.planner.detected_nms_radius_m,
        min_sensor_types=cfg.planner.target_min_sensor_types,
    )


def test_choose_next_goal_uses_mst_route_when_targets_confirmed() -> None:
    cfg = scenario_config("clustered_base", 0, "graph_mst")
    grid = make_grid(cfg.world, cfg.grid)
    prob_map = init_probability_map(grid, cfg.grid)
    state = PlannerState(coverage_route=lawnmower_route(cfg.world, cfg.planner))
    target_queue = _empty_target_queue(cfg)
    det = Detection(sensor="camera", position=np.array([50.0, 60.0]), confidence=0.9, source_index=None)
    target_queue.add_detections([det], t=0.0, world=cfg.world)
    target_queue.add_detections([det], t=1.0, world=cfg.world)
    assert target_queue.confirmed_targets()

    goal, label = choose_next_goal(
        t=0.0,
        current=np.array(cfg.world.depot, dtype=float),
        heading=0.0,
        state=state,
        prob_map=prob_map,
        world=cfg.world,
        robot=cfg.robot,
        planner=cfg.planner,
        fusion=cfg.fusion,
        target_queue=target_queue,
    )

    assert label == "route"
    assert np.allclose(goal, [50.0, 60.0], atol=1.0)


def test_choose_next_goal_falls_back_to_lawnmower_without_confirmed_targets() -> None:
    cfg = scenario_config("clustered_base", 0, "graph_mst")
    grid = make_grid(cfg.world, cfg.grid)
    prob_map = init_probability_map(grid, cfg.grid)
    route = lawnmower_route(cfg.world, cfg.planner)
    state = PlannerState(coverage_route=route)
    target_queue = _empty_target_queue(cfg)

    goal, label = choose_next_goal(
        t=0.0,
        current=np.array(cfg.world.depot, dtype=float),
        heading=0.0,
        state=state,
        prob_map=prob_map,
        world=cfg.world,
        robot=cfg.robot,
        planner=cfg.planner,
        fusion=cfg.fusion,
        target_queue=target_queue,
    )

    assert label == "coverage"
    assert np.allclose(goal, route[0])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_graph_mst.py -v -k choose_next_goal`
Expected: FAIL — both tests get `label == "greedy"` (falls through to the final `next_greedy` fallback in `choose_next_goal`) instead of `"route"`/`"coverage"`.

- [ ] **Step 3: Add `graph_mst` to the `PlannerMode` literal**

In `cleanup_sim/config.py`, change:

```python
PlannerMode = Literal[
    "lawnmower",
    "lawnmower_sparse",
    "lawnmower_dense",
    "greedy",
    "active",
    "detected_tsp",
    "hybrid",
    "active_entropy",
    "active_probability",
    "active_no_distance",
]
```

to:

```python
PlannerMode = Literal[
    "lawnmower",
    "lawnmower_sparse",
    "lawnmower_dense",
    "greedy",
    "active",
    "detected_tsp",
    "graph_mst",
    "hybrid",
    "active_entropy",
    "active_probability",
    "active_no_distance",
]
```

- [ ] **Step 4: Add the `graph_mst` branch to `choose_next_goal`**

In `cleanup_sim/planners.py`, the existing `detected_tsp` branch reads:

```python
    if planner.mode == "detected_tsp":
        confirmed_targets = target_queue.confirmed_targets()
        if confirmed_targets:
            state.current_route = nearest_neighbor_route(current, confirmed_targets, planner.detected_batch_size)
            if state.current_route:
                return state.current_route[0], "route"
        return next_lawnmower(state), "coverage"
```

Insert this new branch directly after it (still before `if planner.mode == "hybrid":`):

```python
    if planner.mode == "graph_mst":
        confirmed_targets = target_queue.confirmed_targets()
        if confirmed_targets:
            state.current_route = mst_route(current, confirmed_targets, planner.detected_batch_size)
            if state.current_route:
                return state.current_route[0], "route"
        return next_lawnmower(state), "coverage"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_graph_mst.py -v`
Expected: `6 passed` (4 from Task 1 + 2 new)

- [ ] **Step 6: Run the full existing suite to check for regressions**

Run: `python -m pytest -q`
Expected: all previously-passing tests still pass (54 + 6 new = 60 passed)

- [ ] **Step 7: Commit**

```bash
git add cleanup_sim/config.py cleanup_sim/planners.py tests/test_graph_mst.py
git commit -m "Wire graph_mst planner mode into choose_next_goal"
```

---

### Task 3: Incremental route invalidation on new confirmed targets

**Files:**
- Modify: `cleanup_sim/planners.py` (add `should_invalidate_graph_route`, near the end of the file, after `pop_arrived_route_goal`)
- Modify: `cleanup_sim/simulation.py` (import + one hook inside `run_simulation`'s sensor-update block)
- Modify: `tests/test_graph_mst.py`

**Interfaces:**
- Consumes: `PlannerState.current_route` field (already exists); `TargetTrack` list returned by `update_detected_targets` (already exists in `cleanup_sim/planners.py`, called from `cleanup_sim/simulation.py`).
- Produces: `should_invalidate_graph_route(mode: str, current_planner_mode: str, confirmations: list) -> bool`. Consumed directly by `cleanup_sim/simulation.py`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_graph_mst.py`:

```python
from cleanup_sim.planners import should_invalidate_graph_route
from cleanup_sim.simulation import run_simulation


def test_should_invalidate_graph_route_only_for_graph_mst_route_with_new_confirmations() -> None:
    assert should_invalidate_graph_route("graph_mst", "route", [object()]) is True
    assert should_invalidate_graph_route("graph_mst", "route", []) is False
    assert should_invalidate_graph_route("graph_mst", "coverage", [object()]) is False
    assert should_invalidate_graph_route("detected_tsp", "route", [object()]) is False


def test_graph_mst_mode_runs_full_simulation_and_records_route_events() -> None:
    cfg = scenario_config("clustered_base", 4, "graph_mst")
    cfg = replace(cfg, robot=replace(cfg.robot, tmax_s=1200.0))
    result = run_simulation(cfg)

    assert result.summary["mode"] == "graph_mst"
    assert np.all(result.belief >= 0.0)
    assert np.all(result.belief <= 1.0)
    events = set(result.events["event"].tolist()) if not result.events.empty else set()
    assert "target_confirmed" in events
    assert "target_routed" in events
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_graph_mst.py -v -k "invalidate or full_simulation"`
Expected: `test_should_invalidate_graph_route_only_for_graph_mst_route_with_new_confirmations` fails with `ImportError: cannot import name 'should_invalidate_graph_route'`. (`test_graph_mst_mode_runs_full_simulation_and_records_route_events` should already pass since Task 2 made `graph_mst` runnable end-to-end — that's fine, it locks in current behavior as a regression guard for Step 4.)

- [ ] **Step 3: Implement `should_invalidate_graph_route`**

In `cleanup_sim/planners.py`, add at the end of the file, after `pop_arrived_route_goal`:

```python
def should_invalidate_graph_route(mode: str, current_planner_mode: str, confirmations: list) -> bool:
    return mode == "graph_mst" and current_planner_mode == "route" and bool(confirmations)
```

- [ ] **Step 4: Wire the invalidation hook into the simulation loop**

In `cleanup_sim/simulation.py`, update the import block:

```python
from .planners import (
    PlannerState,
    choose_next_goal,
    lawnmower_route,
    pop_arrived_route_goal,
    suppress_greedy_region,
    update_detected_targets,
)
```

to:

```python
from .planners import (
    PlannerState,
    choose_next_goal,
    lawnmower_route,
    pop_arrived_route_goal,
    should_invalidate_graph_route,
    suppress_greedy_region,
    update_detected_targets,
)
```

Then, inside `run_simulation`, the sensor-update block currently ends with:

```python
            for det in detections:
                events.append({
                    "time_s": t,
                    "event": "detect",
                    "sensor": det.sensor,
                    "x": float(det.position[0]),
                    "y": float(det.position[1]),
                    "confidence": det.confidence,
                    "source_id": det.source_index,
                })
```

Add this immediately after that `for det in detections:` loop, still inside the `if t - last_sensor_update_t >= config.robot.sensor_period_s:` block (same indentation as the `detections = ...` line above it):

```python
            if should_invalidate_graph_route(config.planner.mode, current_planner_mode, confirmations):
                state.current_route = []
                current_goal = None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_graph_mst.py -v`
Expected: `8 passed`

- [ ] **Step 6: Run the full existing suite to check for regressions**

Run: `python -m pytest -q`
Expected: all tests pass (54 original + 8 new = 62 passed)

- [ ] **Step 7: Commit**

```bash
git add cleanup_sim/planners.py cleanup_sim/simulation.py tests/test_graph_mst.py
git commit -m "Invalidate in-flight graph_mst route when a new target is confirmed"
```

---

### Task 4: Expose `graph_mst` through the CLI entry points

**Files:**
- Modify: `cleanup_sim/run_experiments.py` (`MODE_CHOICES`, lines 18-29 — do NOT touch `DEFAULT_MODES`)
- Modify: `cleanup_sim/run_once.py` (`--mode` choices, line 17)
- Modify: `tests/test_graph_mst.py`

**Interfaces:**
- Consumes: `PlannerMode` from `cleanup_sim/config.py` (Task 2); `scenario_config(scenario, seed, mode)` (existing, unchanged signature).
- Produces: nothing new consumed by later tasks — this is the final task.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_graph_mst.py`:

```python
def test_run_experiments_parser_accepts_graph_mst_mode() -> None:
    from cleanup_sim.run_experiments import build_parser as build_experiments_parser

    args = build_experiments_parser().parse_args(["--modes", "graph_mst"])
    assert args.modes == ["graph_mst"]


def test_run_once_parser_accepts_graph_mst_mode() -> None:
    from cleanup_sim.run_once import build_parser as build_once_parser

    args = build_once_parser().parse_args(["--mode", "graph_mst"])
    assert args.mode == "graph_mst"


def test_graph_mst_excluded_from_default_experiment_modes() -> None:
    from cleanup_sim.run_experiments import DEFAULT_MODES

    assert "graph_mst" not in DEFAULT_MODES
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_graph_mst.py -v -k "run_experiments_parser or run_once_parser"`
Expected: both `argparse`-based tests fail with `SystemExit: 2` (argparse rejects `"graph_mst"` because it isn't in `choices`). `test_graph_mst_excluded_from_default_experiment_modes` already passes (`graph_mst` isn't defined anywhere yet) — that's expected, it's a regression guard, not a driver for this step.

- [ ] **Step 3: Add `graph_mst` to `run_experiments.py` `MODE_CHOICES`**

In `cleanup_sim/run_experiments.py`, change:

```python
MODE_CHOICES: list[PlannerMode] = [
    "lawnmower",
    "lawnmower_sparse",
    "lawnmower_dense",
    "greedy",
    "active_entropy",
    "active_probability",
    "active_no_distance",
    "active",
    "detected_tsp",
    "hybrid",
]
```

to:

```python
MODE_CHOICES: list[PlannerMode] = [
    "lawnmower",
    "lawnmower_sparse",
    "lawnmower_dense",
    "greedy",
    "active_entropy",
    "active_probability",
    "active_no_distance",
    "active",
    "detected_tsp",
    "graph_mst",
    "hybrid",
]
```

Leave `DEFAULT_MODES` untouched — `graph_mst` must stay opt-in only.

- [ ] **Step 4: Add `graph_mst` to `run_once.py` `--mode` choices**

In `cleanup_sim/run_once.py`, change:

```python
    p.add_argument(
        "--mode",
        choices=["lawnmower", "lawnmower_sparse", "lawnmower_dense", "greedy", "active", "detected_tsp", "hybrid"],
        default="active",
    )
```

to:

```python
    p.add_argument(
        "--mode",
        choices=[
            "lawnmower",
            "lawnmower_sparse",
            "lawnmower_dense",
            "greedy",
            "active",
            "detected_tsp",
            "graph_mst",
            "hybrid",
        ],
        default="active",
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_graph_mst.py -v`
Expected: `11 passed`

- [ ] **Step 6: Run the full suite one last time**

Run: `python -m pytest -q`
Expected: all tests pass (54 original + 11 new = 65 passed)

- [ ] **Step 7: Commit**

```bash
git add cleanup_sim/run_experiments.py cleanup_sim/run_once.py tests/test_graph_mst.py
git commit -m "Expose graph_mst mode through run_once/run_experiments CLI"
```

---

## Manual comparison run (not automated, for the user to run themselves)

Once all four tasks are merged on `dev`, compare `graph_mst` against the existing routing strategies with:

```powershell
python -m cleanup_sim.run_experiments `
  --seeds 5 `
  --scenarios clustered_base clustered_noisy uniform_base `
  --modes greedy lawnmower_dense detected_tsp hybrid graph_mst `
  --out-dir out/cleanup_sim/graph_mst_probe `
  --plot-examples
```

Read `out/cleanup_sim/graph_mst_probe/summary.csv` and `aggregate_mean_std.csv` — compare `graph_mst` against `detected_tsp` in particular, since they draw from the same confirmed-target population and differ only in routing order/incrementality.
