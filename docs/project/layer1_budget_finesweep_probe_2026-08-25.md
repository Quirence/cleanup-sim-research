# Layer 1 budget fine-sweep probe, 2026-08-25

## Purpose

This probe checks whether the nominal path budget should remain at the coarse-gate value `2400 m`, move to the previous upper passing value `3600 m`, or use an intermediate budget.

The run is exploratory. It must not be treated as a final statistical experiment because the intermediate budgets use only `3` seeds.

## Commands

The first two attempts were intentionally stopped because they were too expensive for a budget-selection question:

- `2700 3000 3300`, `10` seeds, all modes: stopped after early partial output.
- `2400 2700 3000 3300 3600`, `5` seeds, reduced modes: stopped after early partial output.

The accepted small probe:

```powershell
python -m cleanup_sim_v2.run_layer1 `
  --phase calibration `
  --budgets 2700 3000 3300 `
  --seed-start 240 `
  --seeds 3 `
  --modes belief_horizon adaptive_mission oracle_current_physics `
  --checkpoint `
  --fail-on major `
  --out-root out/cleanup_sim_v2/layer1_budget_finesweep_probe_2026-08-25
```

The command was stopped after the complete `2700 m` and `3000 m` blocks. The partial `3300 m` block is ignored.

## Data Sources

- Heavy reference: `out/cleanup_sim_v2/layer1_postfix_heavy_2026-08-22/layer1_postfix_budget_calibration_2026-08-22/summary_enriched.csv`
- Probe partial: `out/cleanup_sim_v2/layer1_budget_finesweep_probe_2026-08-25/layer1_postfix_budget_calibration_2026-08-22/summary_partial.csv`

Reference endpoints:

- `2400 m` and `3600 m`: `30` seeds from the heavy run.

Intermediate probe:

- `2700 m` and `3000 m`: `3` seeds from this probe.

Because seed counts differ, the intermediate budgets are directional evidence only.

## Selected Results

Mean AUC and final collected ratio for the three selected modes:

| Scenario | Budget, m | Best non-oracle mode | AUC | Collected ratio | Source |
|---|---:|---|---:|---:|---|
| static_calm | 2400 | adaptive_mission | 0.225 | 0.417 | heavy, 30 seeds |
| static_calm | 2700 | belief_horizon | 0.271 | 0.504 | probe, 3 seeds |
| static_calm | 3000 | belief_horizon | 0.295 | 0.527 | probe, 3 seeds |
| static_calm | 3600 | adaptive_mission | 0.310 | 0.537 | heavy, 30 seeds |
| weak_drift | 2400 | adaptive_mission | 0.281 | 0.591 | heavy, 30 seeds |
| weak_drift | 2700 | belief_horizon | 0.371 | 0.740 | probe, 3 seeds |
| weak_drift | 3000 | belief_horizon | 0.408 | 0.740 | probe, 3 seeds |
| weak_drift | 3600 | belief_horizon | 0.414 | 0.734 | heavy, 30 seeds |
| strong_drift | 2400 | adaptive_mission | 0.508 | 0.855 | heavy, 30 seeds |
| strong_drift | 2700 | adaptive_mission | 0.499 | 0.736 | probe, 3 seeds |
| strong_drift | 3000 | adaptive_mission | 0.529 | 0.842 | probe, 3 seeds |
| strong_drift | 3600 | adaptive_mission | 0.630 | 0.887 | heavy, 30 seeds |
| robot_disturbed | 2400 | belief_horizon | 0.307 | 0.666 | heavy, 30 seeds |
| robot_disturbed | 2700 | belief_horizon | 0.373 | 0.807 | probe, 3 seeds |
| robot_disturbed | 3000 | belief_horizon | 0.417 | 0.827 | probe, 3 seeds |
| robot_disturbed | 3600 | belief_horizon | 0.437 | 0.724 | heavy, 30 seeds |

All complete probe runs had zero `time_budget` stops. Non-oracle runs stopped by `path_budget`; oracle runs usually stopped by `done` after collecting all debris.

## Interpretation

`2400 m` should not be treated as finally fixed. It is only the minimum budget that passed the coarse budget gate.

The intermediate probe supports `3000 m` as a plausible nominal candidate:

- It is less harsh than `2400 m`.
- It remains clearly resource-limited for non-oracle modes.
- Oracle still collects all debris in the checked scenarios, so the gap is not caused by an impossible mission.
- In `static_calm`, `weak_drift`, and `robot_disturbed`, `3000 m` approaches the `3600 m` AUC region without using the longer mission budget.
- In `strong_drift`, `3600 m` still looks meaningfully stronger, so the budget choice affects the scientific story.

The probe also reinforces a separate algorithmic point:

- `adaptive_mission` often matches or trails `belief_horizon`.
- In `strong_drift`, their trajectories/results can be effectively identical.
- Current `adaptive_mission` should not be framed as a robustly superior algorithm without further redesign or ablation evidence.

## Recommendation

Do not fix `2400 m` yet.

Use `3000 m` as the next candidate nominal budget and validate it with a modest confirmatory run:

- budgets: `2400`, `3000`, `3600`;
- scenarios: four base scenarios;
- modes: full mode set;
- seeds: `10` first, not `30`;
- decision: choose the smallest budget that preserves oracle feasibility, non-oracle non-saturation, and regime distinguishability.

Only after this 10-seed confirmation should a final 30-seed baseline be launched.

## Scientific Consequence

The budget should be part of the article's regime analysis, not a hidden constant.

The article should describe path budget as a normalized mission resource:

```text
collection_coverage_ratio = path_budget_m * collection_width_m / area_m2
```

For `area = 40000 m^2` and `collection_width = 1 m`:

- `2400 m` corresponds to `6.0%` nominal swept coverage.
- `3000 m` corresponds to `7.5%`.
- `3600 m` corresponds to `9.0%`.

This framing is stronger than claiming that a single path budget is universally correct.
