"""Derive committed-route staleness diagnostics from immutable horizon logs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from cleanup_sim_v2.adaptive_horizon import (
    QUEUE_DIAGNOSTIC_METRICS,
    analyze_horizon_results,
    summarize_horizon_events,
    validate_horizon_matrix,
)
from cleanup_sim_v2.provenance import file_sha256


KEY_COLUMNS = ["scenario", "seed", "horizon_variant"]


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--run-dirs", type=Path, nargs="+", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    if args.out_dir.exists() and any(args.out_dir.iterdir()):
        raise FileExistsError("Use a new audit output directory; existing evidence is immutable")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    summary = pd.read_csv(args.summary)
    validate_horizon_matrix(summary)
    expected_keys = {
        (str(row.scenario), int(row.seed), str(row.horizon_variant))
        for row in summary[KEY_COLUMNS].itertuples(index=False)
    }

    rows: list[dict] = []
    event_inputs: list[dict] = []
    seen_keys: set[tuple[str, int, str]] = set()
    for run_dir in args.run_dirs:
        for manifest_path in sorted(run_dir.glob("*_manifest.json")):
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            run_summary = manifest.get("summary", {})
            if run_summary.get("runner") != "run_adaptive_horizon":
                continue
            key = (
                str(run_summary["scenario"]),
                int(run_summary["seed"]),
                str(run_summary["horizon_variant"]),
            )
            if key in seen_keys:
                raise ValueError(f"Duplicate run manifest for {key}")
            seen_keys.add(key)
            event_record = manifest["artifacts"]["events"]
            event_path = manifest_path.parent / event_record["file"]
            actual_sha256 = file_sha256(event_path)
            if actual_sha256 != event_record["sha256"]:
                raise ValueError(f"Event artifact hash mismatch: {event_path}")
            events = pd.read_csv(event_path, low_memory=False)
            rows.append({
                "scenario": key[0],
                "seed": key[1],
                "horizon_variant": key[2],
                **summarize_horizon_events(events),
            })
            event_inputs.append({
                "key": list(key),
                "path": event_path.as_posix(),
                "sha256": actual_sha256,
            })

    if seen_keys != expected_keys:
        missing = sorted(expected_keys - seen_keys)
        extra = sorted(seen_keys - expected_keys)
        raise ValueError(f"Run/summary key mismatch; missing={missing}, extra={extra}")

    diagnostics = pd.DataFrame(rows).sort_values(KEY_COLUMNS).reset_index(drop=True)
    if not diagnostics["regime_route_snapshot_coverage"].eq(1.0).all():
        raise ValueError("Committed-route regime snapshots are incomplete")
    new_columns = [
        "regime_route_snapshot_coverage",
        "queued_route_assignment_fraction",
        "route_staleness_ratio_mean",
        "route_staleness_ratio_exceedance_fraction",
        "queued_route_staleness_ratio_mean",
    ]
    enriched = summary.merge(
        diagnostics[[*KEY_COLUMNS, *new_columns]],
        on=KEY_COLUMNS,
        validate="one_to_one",
    )
    effects, report = analyze_horizon_results(enriched)
    queue_effects = effects.loc[effects["metric"].isin(QUEUE_DIAGNOSTIC_METRICS)].copy()

    diagnostics_path = args.out_dir / "queue_staleness_by_run.csv"
    effects_path = args.out_dir / "queue_staleness_effects.csv"
    diagnostics.to_csv(diagnostics_path, index=False)
    queue_effects.to_csv(effects_path, index=False)
    _write_json(args.out_dir / "queue_staleness_audit.json", {
        "status": "post_hoc_diagnostic_from_prespecified_event_fields",
        "does_not_change_primary_decision": report["decision"] == "ambiguous",
        "input_summary": {
            "path": args.summary.as_posix(),
            "sha256": file_sha256(args.summary),
            "rows": len(summary),
        },
        "event_artifacts": {
            "count": len(event_inputs),
            "all_manifest_hashes_verified": True,
            "inputs": event_inputs,
        },
        "snapshot_coverage": {
            "minimum": float(diagnostics["regime_route_snapshot_coverage"].min()),
            "maximum": float(diagnostics["regime_route_snapshot_coverage"].max()),
        },
        "metric_definitions": {
            "queued_route_assignment_fraction": "goal_started snapshots with remaining queued points / valid snapshots",
            "route_staleness_ratio_mean": "mean remaining nominal route time / target stale timeout across valid goal_started snapshots; zero when no route remains",
            "route_staleness_ratio_exceedance_fraction": "valid goal_started snapshots where remaining nominal route time exceeds target stale timeout / valid snapshots",
            "queued_route_staleness_ratio_mean": "conditional mean ratio among snapshots with remaining queued points; descriptive only",
        },
        "artifacts": {
            diagnostics_path.name: file_sha256(diagnostics_path),
            effects_path.name: file_sha256(effects_path),
        },
    })
    print(f"validated_runs={len(diagnostics)}; primary_decision={report['decision']}; out={args.out_dir}")


if __name__ == "__main__":
    main()
