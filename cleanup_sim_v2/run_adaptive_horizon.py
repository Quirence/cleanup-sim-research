from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path

import pandas as pd

from .adaptive_horizon import HORIZON_VARIANTS, analyze_horizon_results
from .config import scenario_config
from .io import config_hash, save_run
from .provenance import (
    assert_provenance_unchanged,
    capture_provenance,
    file_sha256,
    summary_provenance,
    validate_resume_configs,
    validate_resume_provenance,
)
from .simulation import run_simulation


REPO_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = REPO_ROOT / "docs/project/adaptive_horizon_experiment_protocol_2026-09-09.md"
DEFAULT_SCENARIOS = ("static_calm", "weak_drift", "strong_drift", "robot_disturbed")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare adaptive route commitment with per-leg replanning.")
    parser.add_argument("--seed-start", type=int, default=400)
    parser.add_argument("--seeds", type=int, default=10)
    parser.add_argument("--scenarios", nargs="+", choices=DEFAULT_SCENARIOS, default=list(DEFAULT_SCENARIOS))
    parser.add_argument("--max-path-m", type=float, default=3000.0)
    parser.add_argument("--tmax-s", type=float, default=16500.0)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    return parser


def _event_metrics(events: pd.DataFrame) -> dict[str, int]:
    starts = events[events["event"] == "goal_started"]
    completed = events[events["event"] == "goal_completed"]

    def total(frame: pd.DataFrame, column: str) -> int:
        if column not in frame:
            return 0
        return int(pd.to_numeric(frame[column], errors="coerce").fillna(0).sum())

    return {
        "selector_invocations": total(starts, "adaptive_selector_invoked"),
        "route_continuations": total(starts, "adaptive_route_continuation"),
        "queue_discarded_points": total(completed, "adaptive_queue_discarded_points"),
    }


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    args = build_parser().parse_args()
    if args.seeds <= 0:
        raise ValueError("--seeds must be positive")
    if not PROTOCOL.is_file():
        raise FileNotFoundError(PROTOCOL)
    if args.out_dir.exists() and any(args.out_dir.iterdir()) and not args.resume:
        raise FileExistsError("Output directory is not empty; use a new directory or --resume")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    partial_path = args.out_dir / "summary_partial.csv"

    provenance = capture_provenance()
    if provenance["git_dirty"]:
        raise RuntimeError("Adaptive horizon experiment requires a clean Git worktree")

    summaries: list[dict] = []
    completed: set[tuple[str, int, str]] = set()
    if args.resume and partial_path.is_file():
        summaries = pd.read_csv(partial_path).to_dict("records")
        validate_resume_provenance(summaries, provenance)
        completed = {
            (str(row["scenario"]), int(row["seed"]), str(row["horizon_variant"]))
            for row in summaries
        }

    configs = {}
    for scenario in args.scenarios:
        for seed in range(args.seed_start, args.seed_start + args.seeds):
            base = scenario_config(scenario, seed, "adaptive_mission", "nominal")
            base = replace(
                base,
                platform=replace(base.platform, max_path_m=args.max_path_m, tmax_s=args.tmax_s),
            )
            for variant, replan in HORIZON_VARIANTS.items():
                configs[(scenario, seed, variant)] = replace(
                    base,
                    planner=replace(base.planner, adaptive_replan_after_each_leg=replan),
                )

    validate_resume_configs(
        summaries,
        {key: config_hash(cfg.to_dict()) for key, cfg in configs.items()},
        ("scenario", "seed", "horizon_variant"),
    )

    for scenario in args.scenarios:
        for seed in range(args.seed_start, args.seed_start + args.seeds):
            for variant in HORIZON_VARIANTS:
                key = (scenario, seed, variant)
                if key in completed:
                    print(f"skip scenario={scenario} seed={seed} horizon={variant} reason=resume", flush=True)
                    continue
                cfg = configs[key]
                result = run_simulation(cfg)
                result.summary.update({
                    "horizon_variant": variant,
                    "adaptive_replan_after_each_leg": cfg.planner.adaptive_replan_after_each_leg,
                    "initial_debris_count": cfg.world.n_debris,
                    "remaining_count": cfg.world.n_debris - int(result.summary["collected"]),
                    "complete_cleanup": int(result.summary["collected"] == cfg.world.n_debris),
                    "config_hash": config_hash(cfg.to_dict()),
                    "runner": "run_adaptive_horizon",
                    **_event_metrics(result.events),
                    **summary_provenance(provenance),
                })
                summaries.append(result.summary)
                prefix = f"{scenario}__adaptive_mission__{variant}__nominal__seed{seed}"
                save_run(result, args.out_dir / "runs", prefix, provenance=provenance)
                pd.DataFrame(summaries).to_csv(partial_path, index=False)
                print(
                    f"done scenario={scenario} seed={seed} horizon={variant} "
                    f"collected={result.summary['collected_ratio']:.3f}",
                    flush=True,
                )

    summary = pd.DataFrame(summaries).sort_values(["scenario", "seed", "horizon_variant"])
    effects, report = analyze_horizon_results(summary)
    summary_path = args.out_dir / "summary.csv"
    effects_path = args.out_dir / "paired_effects.csv"
    report_path = args.out_dir / "analysis_report.json"
    manifest_path = args.out_dir / "experiment_manifest.json"
    summary.to_csv(summary_path, index=False)
    effects.to_csv(effects_path, index=False)
    _write_json(report_path, report)
    _write_json(manifest_path, {
        "runner": "cleanup_sim_v2.run_adaptive_horizon",
        "protocol": str(PROTOCOL.relative_to(REPO_ROOT)).replace("\\", "/"),
        "protocol_sha256": file_sha256(PROTOCOL),
        "provenance": provenance,
        "seed_start": args.seed_start,
        "seeds": args.seeds,
        "scenarios": args.scenarios,
        "horizon_variants": HORIZON_VARIANTS,
        "max_path_m": args.max_path_m,
        "tmax_s": args.tmax_s,
        "rows": len(summary),
        "artifacts": {
            path.name: file_sha256(path)
            for path in (summary_path, effects_path, report_path)
        },
    })
    assert_provenance_unchanged(provenance)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    print(f"manifest: {manifest_path}", flush=True)


if __name__ == "__main__":
    main()
