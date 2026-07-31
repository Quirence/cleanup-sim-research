# Cleanup Sim Hybrid Planner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `cleanup_sim` from a first research prototype into a testable simulator for hybrid probabilistic search-and-collection planning.

**Architecture:** Keep the current package structure and add focused modules for target confirmation, hybrid planning decisions, budget control, ablation modes, and statistical reporting. Existing `active`, `lawnmower`, `greedy`, and `detected_tsp` behavior should remain runnable while the new `hybrid` mode becomes the article's main method.

**Tech Stack:** Python 3.12, NumPy, Pandas, Matplotlib, Pytest, standard-library dataclasses and argparse.

---

## File Structure

- Modify `cleanup_sim/config.py`: extend planner modes and add hybrid/ablation/statistics parameters.
- Create `cleanup_sim/targets.py`: maintain confirmed target tracks without access to ground truth.
- Create `cleanup_sim/hybrid.py`: choose between exploration and target routing.
- Modify `cleanup_sim/planners.py`: integrate target queue and new planner modes.
- Modify `cleanup_sim/simulation.py`: record planner mode events and enforce path/time budgets consistently.
- Modify `cleanup_sim/metrics.py`: add AUC, budgeted metrics, success rates, and target-reaching summaries.
- Modify `cleanup_sim/run_experiments.py`: include hybrid and ablation modes in experiment series.
- Create `cleanup_sim/statistics.py`: paired comparisons, bootstrap confidence intervals, and Holm correction.
- Modify `cleanup_sim/plots.py`: add publication-oriented curves with mean and uncertainty bands.
- Add tests in `tests/test_cleanup_sim.py` and optionally split into `tests/test_targets.py`, `tests/test_hybrid.py`, `tests/test_statistics.py`.
- Update `cleanup_sim/README.md` and `README_WORKFLOW.md` after implementation.

---

## Task 1: Add Planner Modes and Hybrid Parameters

**Files:**
- Modify: `cleanup_sim/config.py`
- Test: `tests/test_cleanup_sim.py`

- [ ] **Step 1: Write the failing test**

Add tests that require `hybrid` and ablation modes to be valid planner modes:

```python
def test_scenario_config_accepts_hybrid_mode() -> None:
    cfg = scenario_config("clustered_base", 0, "hybrid")
    assert cfg.planner.mode == "hybrid"
    assert cfg.planner.hybrid_min_confirmed_targets >= 1
    assert 0.0 < cfg.planner.hybrid_switch_prob <= 1.0


def test_scenario_config_accepts_ablation_modes() -> None:
    for mode in ["active_entropy", "active_probability", "active_no_distance"]:
        cfg = scenario_config("clustered_base", 0, mode)
        assert cfg.planner.mode == mode
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_cleanup_sim.py::test_scenario_config_accepts_hybrid_mode tests/test_cleanup_sim.py::test_scenario_config_accepts_ablation_modes -q
```

Expected: FAIL because `PlannerMode` does not include these modes and config lacks hybrid parameters.

- [ ] **Step 3: Implement minimal config changes**

Update `PlannerMode`:

```python
PlannerMode = Literal[
    "lawnmower",
    "greedy",
    "active",
    "detected_tsp",
    "hybrid",
    "active_entropy",
    "active_probability",
    "active_no_distance",
]
```

Add to `PlannerConfig`:

```python
hybrid_min_confirmed_targets: int = 3
hybrid_switch_prob: float = 0.72
hybrid_explore_entropy_threshold: float = 0.18
hybrid_target_batch_size: int = 8
target_confirm_hits: int = 2
target_stale_after_s: float = 1800.0
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
python -m pytest tests/test_cleanup_sim.py::test_scenario_config_accepts_hybrid_mode tests/test_cleanup_sim.py::test_scenario_config_accepts_ablation_modes -q
```

Expected: PASS.

---

## Task 2: Create Confirmed Target Queue Without Oracle Access

**Files:**
- Create: `cleanup_sim/targets.py`
- Test: `tests/test_targets.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_targets.py`:

```python
from __future__ import annotations

import numpy as np

from cleanup_sim.config import PlannerConfig, WorldConfig
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
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_targets.py -q
```

Expected: FAIL because `cleanup_sim.targets` does not exist.

- [ ] **Step 3: Implement minimal target queue**

Create `cleanup_sim/targets.py`:

```python
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

    @property
    def confirmed(self) -> bool:
        return self.hits > 0


class TargetQueue:
    def __init__(self, confirm_prob: float, confirm_hits: int, nms_radius_m: float) -> None:
        self.confirm_prob = confirm_prob
        self.confirm_hits = confirm_hits
        self.nms_radius_m = nms_radius_m
        self.tracks: list[TargetTrack] = []

    def add_detections(self, detections: list[Detection], t: float, world: WorldConfig) -> None:
        for det in detections:
            if det.confidence < self.confirm_prob:
                continue
            pos = np.clip(det.position.astype(float), [0.0, 0.0], [world.width, world.height])
            match = self._find_match(pos)
            if match is None:
                self.tracks.append(TargetTrack(position=pos, confidence=det.confidence, hits=1, first_seen_s=t, last_seen_s=t))
            else:
                total_hits = match.hits + 1
                match.position = (match.position * match.hits + pos) / total_hits
                match.confidence = max(match.confidence, det.confidence)
                match.hits = total_hits
                match.last_seen_s = t

    def confirmed_targets(self) -> list[np.ndarray]:
        return [track.position.copy() for track in self.tracks if track.confidence >= self.confirm_prob and track.hits >= self.confirm_hits]

    def remove_near(self, position: np.ndarray, radius_m: float) -> int:
        before = len(self.tracks)
        self.tracks = [track for track in self.tracks if np.linalg.norm(track.position - position) > radius_m]
        return before - len(self.tracks)

    def expire_stale(self, t: float, stale_after_s: float) -> int:
        before = len(self.tracks)
        self.tracks = [track for track in self.tracks if t - track.last_seen_s <= stale_after_s]
        return before - len(self.tracks)

    def _find_match(self, position: np.ndarray) -> TargetTrack | None:
        for track in self.tracks:
            if np.linalg.norm(track.position - position) <= self.nms_radius_m:
                return track
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
python -m pytest tests/test_targets.py -q
```

Expected: PASS.

---

## Task 3: Integrate TargetQueue Into Existing Planners

**Files:**
- Modify: `cleanup_sim/planners.py`
- Modify: `cleanup_sim/simulation.py`
- Test: `tests/test_cleanup_sim.py`, `tests/test_targets.py`

- [ ] **Step 1: Write failing test for detected_tsp target source**

Add to `tests/test_cleanup_sim.py`:

```python
from dataclasses import replace


def test_detected_tsp_records_detection_before_target_routing() -> None:
    cfg = scenario_config("clustered_base", 4, "detected_tsp")
    cfg = replace(cfg, robot=replace(cfg.robot, tmax_s=600.0))
    result = run_simulation(cfg)

    events = result.events["event"].tolist() if not result.events.empty else []
    assert "detect" in events
    assert result.summary["mode"] == "detected_tsp"
```

- [ ] **Step 2: Run test to verify current behavior**

Run:

```powershell
python -m pytest tests/test_cleanup_sim.py::test_detected_tsp_records_detection_before_target_routing -q
```

Expected: PASS or FAIL depending on current seed. If it fails due to stochastic no-detection, adjust seed or extend `tmax_s` to 1200.0 before implementation.

- [ ] **Step 3: Replace raw target list with TargetQueue**

In `PlannerState`, replace:

```python
detected_targets: list[np.ndarray] | None = None
```

with:

```python
target_queue: TargetQueue | None = None
```

Initialize in `__post_init__` using planner config where state is created. If direct config injection would make `PlannerState` awkward, keep `PlannerState` simple and create the queue in `run_simulation`, then pass it to `update_detected_targets` and `choose_next_goal`.

- [ ] **Step 4: Update `update_detected_targets`**

Change it to:

```python
def update_detected_targets(target_queue: TargetQueue, detections: list[Detection], planner: PlannerConfig, world: WorldConfig, t: float) -> None:
    target_queue.add_detections(detections, t=t, world=world)
```

- [ ] **Step 5: Update detected_tsp routing**

In `choose_next_goal`, make `detected_tsp` use:

```python
targets = target_queue.confirmed_targets()
state.current_route = nearest_neighbor_route(current, targets, planner.detected_batch_size)
```

Remove visited targets by calling:

```python
target_queue.remove_near(arrived_position, robot.collect_radius_m)
```

Do not use `Detection.source_index` for routing. It may remain in event logs only.

- [ ] **Step 6: Run regression tests**

Run:

```powershell
python -m pytest tests/test_cleanup_sim.py tests/test_targets.py -q
```

Expected: PASS.

---

## Task 4: Add Hybrid Planner Decision Logic

**Files:**
- Create: `cleanup_sim/hybrid.py`
- Modify: `cleanup_sim/planners.py`
- Test: `tests/test_hybrid.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_hybrid.py`:

```python
from __future__ import annotations

import numpy as np

from cleanup_sim.config import PlannerConfig
from cleanup_sim.hybrid import HybridDecision, choose_hybrid_mode


def test_hybrid_routes_when_enough_confirmed_targets_and_low_entropy() -> None:
    planner = PlannerConfig(mode="hybrid", hybrid_min_confirmed_targets=3, hybrid_explore_entropy_threshold=0.2)
    decision = choose_hybrid_mode(mean_entropy=0.12, confirmed_target_count=3, planner=planner)
    assert decision == HybridDecision.ROUTE


def test_hybrid_explores_when_not_enough_targets() -> None:
    planner = PlannerConfig(mode="hybrid", hybrid_min_confirmed_targets=3, hybrid_explore_entropy_threshold=0.2)
    decision = choose_hybrid_mode(mean_entropy=0.12, confirmed_target_count=2, planner=planner)
    assert decision == HybridDecision.EXPLORE


def test_hybrid_explores_when_entropy_is_high_even_with_targets() -> None:
    planner = PlannerConfig(mode="hybrid", hybrid_min_confirmed_targets=3, hybrid_explore_entropy_threshold=0.2)
    decision = choose_hybrid_mode(mean_entropy=0.25, confirmed_target_count=5, planner=planner)
    assert decision == HybridDecision.EXPLORE
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_hybrid.py -q
```

Expected: FAIL because `cleanup_sim.hybrid` does not exist.

- [ ] **Step 3: Implement minimal hybrid decision module**

Create `cleanup_sim/hybrid.py`:

```python
from __future__ import annotations

from enum import Enum

from .config import PlannerConfig


class HybridDecision(str, Enum):
    EXPLORE = "explore"
    ROUTE = "route"


def choose_hybrid_mode(mean_entropy: float, confirmed_target_count: int, planner: PlannerConfig) -> HybridDecision:
    if confirmed_target_count >= planner.hybrid_min_confirmed_targets and mean_entropy <= planner.hybrid_explore_entropy_threshold:
        return HybridDecision.ROUTE
    return HybridDecision.EXPLORE
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
python -m pytest tests/test_hybrid.py -q
```

Expected: PASS.

---

## Task 5: Wire Hybrid Mode Into Goal Selection

**Files:**
- Modify: `cleanup_sim/planners.py`
- Modify: `cleanup_sim/simulation.py`
- Test: `tests/test_cleanup_sim.py`

- [ ] **Step 1: Write failing integration test**

Add:

```python
def test_hybrid_mode_runs_and_records_planner_decisions() -> None:
    cfg = scenario_config("clustered_base", 2, "hybrid")
    cfg = replace(cfg, robot=replace(cfg.robot, tmax_s=800.0))
    result = run_simulation(cfg)

    assert result.summary["mode"] == "hybrid"
    assert np.all(result.belief >= 0.0)
    assert np.all(result.belief <= 1.0)
    assert "planner_mode" in result.series.columns
    assert set(result.series["planner_mode"].dropna()).issubset({"explore", "route"})
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_cleanup_sim.py::test_hybrid_mode_runs_and_records_planner_decisions -q
```

Expected: FAIL because `hybrid` mode is not wired and `planner_mode` series column does not exist.

- [ ] **Step 3: Implement hybrid branch**

In `choose_next_goal`, add mode `"hybrid"`:

```python
if planner.mode == "hybrid":
    confirmed = target_queue.confirmed_targets()
    mean_entropy = float(np.mean(entropy(prob_map.belief)))
    decision = choose_hybrid_mode(mean_entropy, len(confirmed), planner)
    if decision == HybridDecision.ROUTE and confirmed:
        state.current_route = nearest_neighbor_route(current, confirmed, planner.hybrid_target_batch_size)
        if state.current_route:
            return state.current_route[0], decision.value
    return next_active(current, heading, prob_map, world, planner, fusion), decision.value
```

If changing the return type of `choose_next_goal`, update all callers to receive `(goal, planner_mode_label)`. Existing modes should return labels:

```python
"coverage" for lawnmower fallback
"greedy" for greedy
"active" for active
"route" for detected_tsp target routing
```

- [ ] **Step 4: Record planner mode in time series**

Extend `TimeSeries` with:

```python
planner_mode: list[str]
```

Append the current planner mode label each simulation step and add it to `series_df`.

- [ ] **Step 5: Run integration test**

Run:

```powershell
python -m pytest tests/test_cleanup_sim.py::test_hybrid_mode_runs_and_records_planner_decisions -q
```

Expected: PASS.

---

## Task 6: Add Ablation Planner Modes

**Files:**
- Modify: `cleanup_sim/planners.py`
- Test: `tests/test_hybrid.py`

- [ ] **Step 1: Write failing tests for candidate scoring**

Add:

```python
from cleanup_sim.config import scenario_config
from cleanup_sim.mapping import init_probability_map, make_grid
from cleanup_sim.planners import next_active


def test_active_ablation_modes_return_waypoints_inside_world() -> None:
    for mode in ["active_entropy", "active_probability", "active_no_distance"]:
        cfg = scenario_config("clustered_base", 0, mode)
        grid = make_grid(cfg.world, cfg.grid)
        prob_map = init_probability_map(grid, cfg.grid)
        point = next_active(np.array([10.0, 100.0]), 0.0, prob_map, cfg.world, cfg.planner, cfg.fusion)
        assert 0.0 <= point[0] <= cfg.world.width
        assert 0.0 <= point[1] <= cfg.world.height
```

- [ ] **Step 2: Run test to verify it fails if modes not handled**

Run:

```powershell
python -m pytest tests/test_hybrid.py::test_active_ablation_modes_return_waypoints_inside_world -q
```

Expected: FAIL if mode dispatch does not handle ablations.

- [ ] **Step 3: Implement scoring switches**

Inside `_score_candidate`, compute terms separately:

```python
entropy_value = float(np.sum(h[mask]))
probability_value = float(np.sum(b[mask]))
candidate_value = float(np.sum(candidate[mask]))
distance_penalty = planner.active_lambda * travel
```

Return:

```python
if planner.mode == "active_entropy":
    return entropy_value - distance_penalty
if planner.mode == "active_probability":
    return planner.active_mu * probability_value - distance_penalty
if planner.mode == "active_no_distance":
    return entropy_value + planner.active_alpha * candidate_value + planner.active_mu * probability_value + planner.active_local_collect_weight * local_collect_value
return entropy_value + planner.active_alpha * candidate_value + planner.active_mu * probability_value + planner.active_local_collect_weight * local_collect_value - distance_penalty
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m pytest tests/test_hybrid.py tests/test_cleanup_sim.py -q
```

Expected: PASS.

---

## Task 7: Enforce Equal Budgets and Budgeted Metrics

**Files:**
- Modify: `cleanup_sim/config.py`
- Modify: `cleanup_sim/simulation.py`
- Modify: `cleanup_sim/metrics.py`
- Test: `tests/test_cleanup_sim.py`

- [ ] **Step 1: Write failing test**

Add:

```python
def test_simulation_respects_max_path_budget() -> None:
    cfg = scenario_config("clustered_base", 1, "active")
    robot = replace(cfg.robot, tmax_s=7200.0)
    cfg = replace(cfg, robot=robot)
    cfg = replace(cfg, planner=replace(cfg.planner, max_path_m=500.0))

    result = run_simulation(cfg)

    assert result.summary["path_length_m"] <= 502.0
    assert result.summary["stop_reason"] in {"path_budget", "done"}
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_cleanup_sim.py::test_simulation_respects_max_path_budget -q
```

Expected: FAIL because `max_path_m` and `stop_reason` do not exist.

- [ ] **Step 3: Add budget parameter**

Add to `PlannerConfig`:

```python
max_path_m: float = 14400.0
```

- [ ] **Step 4: Stop simulation on path budget**

In `run_simulation`, after `total_path_m += step_m`, if `total_path_m >= config.planner.max_path_m`, set `stop_reason = "path_budget"` and break.

Set default `stop_reason = "time_budget"`, change to `"done"` when all debris is collected.

- [ ] **Step 5: Add stop reason to summary**

Add `stop_reason` to `summarize_run` input and output.

- [ ] **Step 6: Run test**

Run:

```powershell
python -m pytest tests/test_cleanup_sim.py::test_simulation_respects_max_path_budget -q
```

Expected: PASS.

---

## Task 8: Add Collection Curve AUC and Fixed-Budget Scores

**Files:**
- Modify: `cleanup_sim/metrics.py`
- Test: `tests/test_metrics.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_metrics.py`:

```python
from __future__ import annotations

from cleanup_sim.metrics import auc_collected_ratio, value_at_budget


def test_value_at_budget_returns_last_known_value_before_budget() -> None:
    assert value_at_budget([0.0, 10.0, 20.0], [0.0, 0.2, 0.5], 15.0) == 0.2
    assert value_at_budget([0.0, 10.0, 20.0], [0.0, 0.2, 0.5], 25.0) == 0.5


def test_auc_collected_ratio_normalizes_by_budget() -> None:
    auc = auc_collected_ratio([0.0, 10.0], [0.0, 1.0], budget=10.0)
    assert 0.49 <= auc <= 0.51
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_metrics.py -q
```

Expected: FAIL because functions do not exist.

- [ ] **Step 3: Implement metric helpers**

Add:

```python
def value_at_budget(xs: list[float], ys: list[float], budget: float) -> float:
    value = ys[0] if ys else 0.0
    for x, y in zip(xs, ys):
        if x <= budget:
            value = y
        else:
            break
    return float(value)


def auc_collected_ratio(xs: list[float], ratios: list[float], budget: float) -> float:
    if not xs or not ratios or budget <= 0:
        return 0.0
    x = [0.0]
    y = [ratios[0]]
    for xi, yi in zip(xs, ratios):
        if xi <= budget:
            x.append(float(xi))
            y.append(float(yi))
    if x[-1] < budget:
        x.append(float(budget))
        y.append(y[-1])
    return float(np.trapz(y, x) / budget)
```

Add summary fields for collection ratio at 2, 4, 6, 8, 10, 12 km and AUC by path.

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m pytest tests/test_metrics.py tests/test_cleanup_sim.py -q
```

Expected: PASS.

---

## Task 9: Add Statistical Reporting

**Files:**
- Create: `cleanup_sim/statistics.py`
- Modify: `cleanup_sim/run_experiments.py`
- Test: `tests/test_statistics.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_statistics.py`:

```python
from __future__ import annotations

import pandas as pd

from cleanup_sim.statistics import bootstrap_ci, holm_adjust, paired_differences


def test_paired_differences_aligns_by_seed() -> None:
    df = pd.DataFrame({
        "scenario": ["s", "s", "s", "s"],
        "mode": ["a", "b", "a", "b"],
        "seed": [0, 0, 1, 1],
        "collected_ratio": [0.5, 0.7, 0.6, 0.8],
    })
    diffs = paired_differences(df, scenario="s", mode_a="b", mode_b="a", metric="collected_ratio")
    assert diffs == [0.2, 0.2]


def test_holm_adjust_monotonic() -> None:
    adjusted = holm_adjust([0.01, 0.04, 0.03])
    assert len(adjusted) == 3
    assert all(0.0 <= p <= 1.0 for p in adjusted)


def test_bootstrap_ci_contains_mean_for_constant_values() -> None:
    low, high = bootstrap_ci([0.5, 0.5, 0.5], seed=0)
    assert low == 0.5
    assert high == 0.5
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_statistics.py -q
```

Expected: FAIL because `cleanup_sim.statistics` does not exist.

- [ ] **Step 3: Implement minimal statistics module**

Implement:

- `paired_differences(summary_df, scenario, mode_a, mode_b, metric) -> list[float]`
- `bootstrap_ci(values, seed=0, n=2000, alpha=0.05) -> tuple[float, float]`
- `holm_adjust(p_values) -> list[float]`

Use only NumPy/Pandas and avoid SciPy dependency unless already installed.

- [ ] **Step 4: Add CSV output**

In `run_experiments.py`, after `aggregate_mean_std.csv`, write:

```text
paired_comparisons.csv
```

Compare `hybrid` against `lawnmower`, `greedy`, `active`, `detected_tsp` for:

- `collected_ratio`
- `path_to_80_m`
- `auc_collected_by_path`
- `false_visits`
- `brier_score`

- [ ] **Step 5: Run tests**

Run:

```powershell
python -m pytest tests/test_statistics.py tests/test_cleanup_sim.py -q
```

Expected: PASS.

---

## Task 10: Update Experiment Modes and Smoke Runs

**Files:**
- Modify: `cleanup_sim/run_experiments.py`
- Test: `tests/test_cleanup_sim.py`

- [ ] **Step 1: Write failing test**

Add:

```python
from cleanup_sim.run_experiments import DEFAULT_MODES


def test_default_experiment_modes_include_hybrid_and_ablations() -> None:
    assert "hybrid" in DEFAULT_MODES
    assert "active_entropy" in DEFAULT_MODES
    assert "active_probability" in DEFAULT_MODES
    assert "active_no_distance" in DEFAULT_MODES
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_cleanup_sim.py::test_default_experiment_modes_include_hybrid_and_ablations -q
```

Expected: FAIL because defaults do not include new modes.

- [ ] **Step 3: Update defaults**

Set:

```python
DEFAULT_MODES: list[PlannerMode] = [
    "lawnmower",
    "greedy",
    "active_entropy",
    "active_probability",
    "active_no_distance",
    "active",
    "detected_tsp",
    "hybrid",
]
```

- [ ] **Step 4: Run smoke experiment**

Run:

```powershell
python -m cleanup_sim.run_experiments --seeds 2 --scenarios clustered_base --modes lawnmower greedy active detected_tsp hybrid --out-dir out/cleanup_sim/smoke_hybrid --plot-examples
```

Expected:

- `out/cleanup_sim/smoke_hybrid/summary.csv`
- `out/cleanup_sim/smoke_hybrid/aggregate_mean_std.csv`
- `out/cleanup_sim/smoke_hybrid/paired_comparisons.csv`
- figures for seed 0.

---

## Task 11: Update Plots for Article-Oriented Outputs

**Files:**
- Modify: `cleanup_sim/plots.py`
- Test: smoke run output inspection

- [ ] **Step 1: Add plot requirements**

The experiment plot directory must include:

- `*_mean_collected_vs_path.png`
- `*_mean_collected_vs_time.png`
- `*_map_quality_by_mode.png`
- `*_false_visits_by_mode.png`

- [ ] **Step 2: Implement mean curves**

Read `runs/*_series.csv`, group by scenario/mode, interpolate collected ratio over a common path/time grid, plot mean and 95% bootstrap band or mean +/- std.

- [ ] **Step 3: Implement bar plots**

Use `aggregate_mean_std.csv` to plot:

- Brier score by mode;
- final entropy by mode;
- false visits by mode.

- [ ] **Step 4: Run smoke experiment with plots**

Run:

```powershell
python -m cleanup_sim.run_experiments --seeds 2 --scenarios clustered_base --modes active detected_tsp hybrid --out-dir out/cleanup_sim/smoke_plots --plot-examples
```

Expected: plot files exist and are non-empty.

---

## Task 12: Documentation and Final Verification

**Files:**
- Modify: `cleanup_sim/README.md`
- Modify: `README_WORKFLOW.md`
- Create: `docs/article/results/hybrid_simulator_validation.md`

- [ ] **Step 1: Update simulator README**

Document:

- all planner modes;
- hybrid decision rule;
- target confirmation rule;
- path budget;
- experiment outputs;
- smoke commands;
- full experiment command.

- [ ] **Step 2: Create validation summary**

Create `docs/article/results/hybrid_simulator_validation.md` with:

- implemented simulator changes;
- test commands and results;
- smoke experiment command;
- generated output files;
- remaining limitations.

- [ ] **Step 3: Run full test suite**

Run:

```powershell
python -m pytest tests -q
```

Expected: all tests pass.

- [ ] **Step 4: Run representative experiment**

Run:

```powershell
python -m cleanup_sim.run_experiments --seeds 5 --scenarios clustered_base clustered_noisy uniform_base --modes lawnmower greedy active detected_tsp hybrid --out-dir out/cleanup_sim/hybrid_validation --plot-examples
```

Expected: outputs are produced without exceptions.

- [ ] **Step 5: Acceptance check**

Accept this milestone only if:

- `hybrid` runs end-to-end;
- `detected_tsp` uses confirmed detections, not ground truth;
- path budget is enforced;
- ablation modes run;
- summary includes AUC and fixed-budget metrics;
- paired comparison CSV exists;
- tests pass;
- README documents the workflow.

---

## Implementation Order

1. Task 1: config modes.
2. Task 2: target queue.
3. Task 3: planner integration.
4. Task 4: hybrid decision.
5. Task 5: hybrid run loop.
6. Task 6: ablations.
7. Task 7: equal budgets.
8. Task 8: budgeted metrics.
9. Task 9: statistics.
10. Task 10: experiment defaults.
11. Task 11: plots.
12. Task 12: docs and verification.

## Notes for Scientific Interpretation

- If `hybrid` is worse than `detected_tsp`, do not hide this. Interpret `detected_tsp` as strong target-routing baseline and discuss where hybrid helps before enough targets are confirmed.
- If `hybrid` beats `active` only under some noise/scenario settings, present that as the main scientific result: areas of applicability.
- If ablations show that one coefficient dominates, reduce novelty claims and frame the article as a comparative simulation study.
- Never claim real CV, SLAM, NMHE, NMPC, or field validation from this simulator milestone.

