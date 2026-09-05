# Project Context

Start with `docs/project/current_state.md`, then read
`docs/project/project_memory_snapshot_2026-09-05.md` and
`docs/project/adaptive_mission_revision_review_2026-09-05.md`.
These are the current handoff documents; dated older reports preserve history.

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

- Inspect the current branch and local diff before editing. Several worktrees
  exist; the directory called `datascience` may not contain the latest work.
- Preserve collaborator commits and original experiment files. `out/` is not
  globally ignored: stage individual evidence files, never all generated output.
- Record implementation changes, evidence, limitations, and next steps in the
  handoff documents. Run focused tests and `python -m pytest` for shared changes.
- To rebuild the review tables without running simulations:
  `python -m scripts.audit_adaptive_evidence --out-dir out/audit/adaptive_evidence`.
- Distinguish selector invocations from queued route legs. Old traces without
  invocation markers cannot establish selector frequencies.
- The colleague's post-change CSV records a dirty source tree; a local control
  did not reproduce one row. Resolve provenance/environment before using those
  data for final claims. Do not overwrite the original CSV to match a rerun.
