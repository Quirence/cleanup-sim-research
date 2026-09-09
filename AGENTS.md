# Project Context

Start with `docs/project/current_state.md`, then read
`docs/project/next_research_plan.md`. These are the two canonical handoff
documents. Dated reports preserve evidence and history but are not active plans.

## Research Direction

- Study USV mission planning for floating-debris search and collection with
  incomplete, noisy, aging observations. The intended result is a validated
  method for identifying useful mission regimes from measurable conditions.
- Treat `adaptive_mission` as an experimental decision rule. Do not assume it
  must beat every baseline, or treat a simulator alone as the scientific result.
- Use `cleanup_sim_v2`. `cleanup_sim` and pre-v2.1 results are historical.
- Keep assumptions explicit: no validated CV/radar hardware, CFD, SLAM,
  NMHE/NMPC, or mathematically optimal oracle.
- Seeds 100-129 were already used in the 3840-run budget calibration. They
  cannot serve as an untouched final sample after inspecting those results.
- Budget 3000 m is a diagnostic candidate, not a frozen universal setting.

## Workflow

- Inspect the current branch and local diff before editing. Use `main` after the
  2026-09-07 consolidation; do not resume work from an older worktree.
- Preserve collaborator commits and original experiment files. New `out/`
  content is ignored by default. Put durable evidence in
  `docs/project/evidence/`, or force-add only an explicitly reviewed result set.
- Record implementation changes, evidence, limitations, and next steps in the
  handoff documents. Run focused tests and `python -m pytest` for shared changes.
- To rebuild the review tables without running simulations:
  `python -m scripts.audit_adaptive_evidence --out-dir out/audit/adaptive_evidence`.
- Distinguish selector invocations from queued route legs. Old traces without
  invocation markers cannot establish selector frequencies.
- The colleague's post-change CSV records a dirty source tree; a local control
  did not reproduce one row. Resolve provenance/environment before using those
  data for final claims. Do not overwrite the original CSV to match a rerun.
- User decision on 2026-09-08: historical discrepancy investigation is deferred
  to the colleague. Do not resume it unless requested. It does not block drafting,
  development experiments, or confirmation on independently verified new data.
  Keep the uncertain historical series diagnostic.
- The colleague's bounded task, inputs, and completion criteria are in
  `docs/project/colleague_historical_reproducibility_task_2026-09-09.md`.
- The active test suite covers only `cleanup_sim_v2`. Legacy v1 tests are kept
  in Git history and in branch `archive/belief-hypotheses-20260813`.
