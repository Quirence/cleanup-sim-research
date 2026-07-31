# hybrid_mst Planner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new planner mode `hybrid_mst` that reuses `hybrid`'s explore/route switch (`choose_hybrid_mode`) and its `active`-mode exploration exactly as-is, but routes to confirmed targets via `mst_route` (Prim MST + preorder-DFS, already implemented for `graph_mst`) instead of `nearest_neighbor_route`, and reuses the existing incremental route-invalidation hook so it also applies to this mode.

**Architecture:** Two additive changes to `cleanup_sim/planners.py` (a new `choose_next_goal` branch that mirrors the existing `hybrid` branch, and a one-line generalization of `should_invalidate_graph_route`'s mode check), one `PlannerMode` literal addition in `cleanup_sim/config.py`, and CLI `choices` additions in `cleanup_sim/run_once.py` / `cleanup_sim/run_experiments.py`. No changes to `cleanup_sim/hybrid.py`, `cleanup_sim/simulation.py`, or `mst_route` itself — all three are reused unmodified.

**Tech Stack:** Python 3.11/3.12, numpy, pandas, pytest (existing project stack).

## Global Constraints

- Work happens on git branch `dev` (already checked out); do not merge to `main` as part of this plan.
- Do not modify `cleanup_sim/confirmatory.py` or any file under `docs/article/stage2/`.
- Do not add new `PlannerConfig` fields — `hybrid_mst` reuses `hybrid_min_confirmed_targets`, `hybrid_explore_entropy_threshold`, `hybrid_target_batch_size` exactly as `hybrid` does.
- Do not modify `cleanup_sim/hybrid.py` — `choose_hybrid_mode` is used unchanged.
- Do not modify `mst_route` or `nearest_neighbor_route` in `cleanup_sim/planners.py` — only add a new dispatch branch that calls the existing `mst_route`.
- Add `hybrid_mst` to CLI `choices` lists but NOT to `DEFAULT_MODES` in `cleanup_sim/run_experiments.py` — stays opt-in.
- Match existing code style: `from __future__ import annotations`, type hints, no comments unless explaining non-obvious behavior.
- **Acceptance requires a comparison run**, not just passing tests: after implementation, run
  `python -m cleanup_sim.run_experiments --seeds 5 --scenarios clustered_base clustered_noisy uniform_base --modes greedy lawnmower_dense detected_tsp hybrid graph_mst hybrid_mst --out-dir out/cleanup_sim/hybrid_mst_probe --plot-examples`
  and compare the resulting `aggregate_mean_std.csv` against the existing `out/cleanup_sim/graph_mst_probe/aggregate_mean_std.csv` (same seeds/scenarios/budgets, so the pre-existing modes' numbers should reproduce exactly — the simulation is fully seed-deterministic). This step is NOT part of either task below — the controller runs it directly after both tasks are reviewed and approved, and reports the comparison to the user.

---

### Task 1: `hybrid_mst` core wiring — dispatch branch + invalidation

**Files:**
- Modify: `cleanup_sim/config.py` (`PlannerMode` literal — currently lines 9-20, insert `"hybrid_mst"` right after `"hybrid"`)
- Modify: `cleanup_sim/planners.py` (new `choose_next_goal` branch after the existing `hybrid` branch, currently lines 255-263, before the `active_modes = {...}` line 264; and the `should_invalidate_graph_route` function, currently the last 2 lines of the file)
- Modify: `tests/test_graph_mst.py`

**Interfaces:**
- Consumes: `mst_route(start, targets, limit)` (Task 1 of the prior `graph_mst` plan, already in `cleanup_sim/planners.py`); `choose_hybrid_mode(mean_entropy, confirmed_target_count, planner) -> HybridDecision` and `HybridDecision` enum from `cleanup_sim/hybrid.py` (already imported in `planners.py` at line 8); `next_active(current, heading, prob_map, world, planner, fusion) -> np.ndarray` (already in `planners.py`).
- Produces: `choose_next_goal(..., planner.mode="hybrid_mst", ...)` returns `(goal, "route")` when the hybrid switch selects ROUTE and confirmed targets exist (route built via `mst_route`), `(goal, "explore")` otherwise. `should_invalidate_graph_route` now returns `True` for `mode in {"graph_mst", "hybrid_mst"}` (previously only `"graph_mst"`) — consumed unchanged by the existing hook in `cleanup_sim/simulation.py`, no changes needed there.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_graph_mst.py` (the file already imports `replace`, `numpy as np`, `scenario_config`, `init_probability_map`, `make_grid`, `PlannerState`, `choose_next_goal`, `lawnmower_route`, `mst_route`, `nearest_neighbor_route`, `should_invalidate_graph_route`, `Detection`, `run_simulation`, `TargetQueue` — reuse the existing `_empty_target_queue` helper already defined in the file):

```python
def test_choose_next_goal_hybrid_mst_explores_when_switch_selects_explore() -> None:
    cfg = scenario_config("clustered_base", 0, "hybrid_mst")
    grid = make_grid(cfg.world, cfg.grid)
    prob_map = init_probability_map(grid, cfg.grid)
    state = PlannerState(coverage_route=lawnmower_route(cfg.world, cfg.planner))
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

    assert label == "explore"
    assert not state.current_route


def test_choose_next_goal_hybrid_mst_routes_via_mst_not_nearest_neighbor() -> None:
    cfg = scenario_config("clustered_base", 0, "hybrid_mst")
    grid = make_grid(cfg.world, cfg.grid)
    prob_map = init_probability_map(grid, cfg.grid)
    prob_map.belief.fill(0.02)
    state = PlannerState(coverage_route=lawnmower_route(cfg.world, cfg.planner))
    target_queue = _empty_target_queue(cfg)
    # Offset by the depot position (10, 100) from the branching layout verified in
    # cleanup_sim/planners.py's mst_route tests — MST/nearest-neighbor divergence
    # depends on the geometry relative to `start`, so the points must move with it.
    positions = [(48.1, 143.0), (58.9, 197.6), (87.6, 130.9), (37.0, 186.3), (98.1, 151.1)]
    for pos in positions:
        det_camera = Detection(sensor="camera", position=np.array(pos), confidence=0.9, source_index=None)
        det_radar = Detection(sensor="radar", position=np.array(pos), confidence=0.9, source_index=None)
        target_queue.add_detections([det_camera], t=0.0, world=cfg.world)
        target_queue.add_detections([det_radar], t=1.0, world=cfg.world)
    confirmed = target_queue.confirmed_targets()
    assert len(confirmed) == 5
    start = np.array(cfg.world.depot, dtype=float)

    goal, label = choose_next_goal(
        t=0.0,
        current=start,
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
    mst_order = [tuple(p) for p in mst_route(start, confirmed, cfg.planner.hybrid_target_batch_size)]
    nn_order = [tuple(p) for p in nearest_neighbor_route(start, confirmed, cfg.planner.hybrid_target_batch_size)]
    actual_order = [tuple(p) for p in state.current_route]
    assert actual_order == mst_order
    assert actual_order != nn_order
    assert np.allclose(goal, mst_order[0])


def test_should_invalidate_graph_route_also_covers_hybrid_mst() -> None:
    assert should_invalidate_graph_route("hybrid_mst", "route", [object()]) is True
    assert should_invalidate_graph_route("hybrid_mst", "route", []) is False
    assert should_invalidate_graph_route("hybrid_mst", "explore", [object()]) is False
    assert should_invalidate_graph_route("hybrid", "route", [object()]) is False


def test_hybrid_mst_mode_runs_full_simulation_and_records_route_events() -> None:
    cfg = scenario_config("clustered_base", 4, "hybrid_mst")
    cfg = replace(cfg, robot=replace(cfg.robot, tmax_s=1200.0))
    result = run_simulation(cfg)

    assert result.summary["mode"] == "hybrid_mst"
    assert np.all(result.belief >= 0.0)
    assert np.all(result.belief <= 1.0)
    assert "planner_mode" in result.series.columns
    assert set(result.series["planner_mode"].dropna()).issubset({"explore", "route", "return"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_graph_mst.py -v -k hybrid_mst`
Expected:
- `test_choose_next_goal_hybrid_mst_explores_when_switch_selects_explore` and `test_choose_next_goal_hybrid_mst_routes_via_mst_not_nearest_neighbor` FAIL — `scenario_config("clustered_base", 0, "hybrid_mst")` still constructs a `PlannerConfig(mode="hybrid_mst")` (the `Literal` isn't enforced at runtime), but `choose_next_goal` has no `"hybrid_mst"` branch yet, so it falls through to the final `next_greedy` fallback and returns `label == "greedy"` instead of `"explore"`/`"route"`.
- `test_should_invalidate_graph_route_also_covers_hybrid_mst` FAILS — the first assertion `should_invalidate_graph_route("hybrid_mst", "route", [object()]) is True` fails because the function currently only checks `mode == "graph_mst"`.
- `test_hybrid_mst_mode_runs_full_simulation_and_records_route_events` FAILS — `result.summary["mode"]` will be `"hybrid_mst"` (that part is fine, `summarize_run` just echoes `config.planner.mode`), but the mode falls through to the `greedy` dispatch branch in `choose_next_goal`, so `result.series["planner_mode"]` will contain `"greedy"`, which is not a subset of `{"explore", "route", "return"}` — the `assert set(...).issubset(...)` fails.

- [ ] **Step 3: Add `hybrid_mst` to the `PlannerMode` literal**

In `cleanup_sim/config.py`, change:

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
    "hybrid_mst",
    "active_entropy",
    "active_probability",
    "active_no_distance",
]
```

- [ ] **Step 4: Add the `hybrid_mst` branch to `choose_next_goal`**

In `cleanup_sim/planners.py`, the existing `hybrid` branch (lines 255-263) reads:

```python
    if planner.mode == "hybrid":
        confirmed_targets = target_queue.confirmed_targets()
        mean_entropy = float(np.mean(entropy(prob_map.belief)))
        decision = choose_hybrid_mode(mean_entropy, len(confirmed_targets), planner)
        if decision == HybridDecision.ROUTE and confirmed_targets:
            state.current_route = nearest_neighbor_route(current, confirmed_targets, planner.hybrid_target_batch_size)
            if state.current_route:
                return state.current_route[0], decision.value
        return next_active(current, heading, prob_map, world, planner, fusion), decision.value
```

Insert this new branch directly after it (still before `active_modes = {...}`):

```python
    if planner.mode == "hybrid_mst":
        confirmed_targets = target_queue.confirmed_targets()
        mean_entropy = float(np.mean(entropy(prob_map.belief)))
        decision = choose_hybrid_mode(mean_entropy, len(confirmed_targets), planner)
        if decision == HybridDecision.ROUTE and confirmed_targets:
            state.current_route = mst_route(current, confirmed_targets, planner.hybrid_target_batch_size)
            if state.current_route:
                return state.current_route[0], decision.value
        return next_active(current, heading, prob_map, world, planner, fusion), decision.value
```

- [ ] **Step 5: Generalize `should_invalidate_graph_route`**

In `cleanup_sim/planners.py`, the function currently reads (last lines of the file):

```python
def should_invalidate_graph_route(mode: str, goal_label: str, confirmations: list[TargetTrack]) -> bool:
    return mode == "graph_mst" and goal_label == "route" and bool(confirmations)
```

Change to:

```python
def should_invalidate_graph_route(mode: str, goal_label: str, confirmations: list[TargetTrack]) -> bool:
    return mode in {"graph_mst", "hybrid_mst"} and goal_label == "route" and bool(confirmations)
```

`cleanup_sim/simulation.py` already calls this function generically with `config.planner.mode` — no changes needed there; `hybrid_mst` automatically gets the same incremental-invalidation behavior as `graph_mst`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_graph_mst.py -v`
Expected: `17 passed` (13 existing + 4 new)

- [ ] **Step 7: Run the full existing suite to check for regressions**

Run: `python3 -m pytest -q`
Expected: `71 passed` (67 existing + 4 new)

- [ ] **Step 8: Commit**

```bash
git add cleanup_sim/config.py cleanup_sim/planners.py tests/test_graph_mst.py
git commit -m "Add hybrid_mst: hybrid explore/route switch with MST-based routing"
```

---

### Task 2: Expose `hybrid_mst` through the CLI entry points

**Files:**
- Modify: `cleanup_sim/run_experiments.py` (`MODE_CHOICES` — do NOT touch `DEFAULT_MODES`)
- Modify: `cleanup_sim/run_once.py` (`--mode` choices)
- Modify: `tests/test_graph_mst.py`

**Interfaces:**
- Consumes: `PlannerMode` from `cleanup_sim/config.py` (Task 1); `scenario_config(scenario, seed, mode)` (existing, unchanged signature).
- Produces: nothing consumed by later work — this is the final task in this plan.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_graph_mst.py`:

```python
def test_run_experiments_parser_accepts_hybrid_mst_mode() -> None:
    from cleanup_sim.run_experiments import build_parser as build_experiments_parser

    args = build_experiments_parser().parse_args(["--modes", "hybrid_mst"])
    assert args.modes == ["hybrid_mst"]


def test_run_once_parser_accepts_hybrid_mst_mode() -> None:
    from cleanup_sim.run_once import build_parser as build_once_parser

    args = build_once_parser().parse_args(["--mode", "hybrid_mst"])
    assert args.mode == "hybrid_mst"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_graph_mst.py -v -k "run_experiments_parser_accepts_hybrid_mst or run_once_parser_accepts_hybrid_mst"`
Expected: both FAIL with `SystemExit: 2` — argparse rejects `"hybrid_mst"` because it isn't yet in either `choices` list.

- [ ] **Step 3: Add `hybrid_mst` to `run_experiments.py` `MODE_CHOICES`**

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
    "graph_mst",
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
    "hybrid_mst",
]
```

Leave `DEFAULT_MODES` untouched — `hybrid_mst` must stay opt-in only.

- [ ] **Step 4: Add `hybrid_mst` to `run_once.py` `--mode` choices**

In `cleanup_sim/run_once.py`, change:

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
            "hybrid_mst",
        ],
        default="active",
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_graph_mst.py -v`
Expected: `19 passed`

- [ ] **Step 6: Run the full suite one last time**

Run: `python3 -m pytest -q`
Expected: `73 passed` (67 existing + 6 new)

- [ ] **Step 7: Commit**

```bash
git add cleanup_sim/run_experiments.py cleanup_sim/run_once.py tests/test_graph_mst.py
git commit -m "Expose hybrid_mst mode through run_once/run_experiments CLI"
```

---

## Post-plan step (controller, not a task): comparison run

After both tasks are implemented and reviewed, run (from the repo's `.venv`):

```bash
.venv/bin/python -m cleanup_sim.run_experiments \
  --seeds 5 \
  --scenarios clustered_base clustered_noisy uniform_base \
  --modes greedy lawnmower_dense detected_tsp hybrid graph_mst hybrid_mst \
  --out-dir out/cleanup_sim/hybrid_mst_probe \
  --plot-examples
```

Compare `out/cleanup_sim/hybrid_mst_probe/aggregate_mean_std.csv` against
`out/cleanup_sim/graph_mst_probe/aggregate_mean_std.csv` row-by-row for the
shared modes (should match, seeds are deterministic) and report where
`hybrid_mst` lands relative to `greedy`/`lawnmower_dense`/`hybrid`/`graph_mst`.
