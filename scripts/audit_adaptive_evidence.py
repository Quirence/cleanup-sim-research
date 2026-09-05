"""Rebuild the September review tables from committed August experiment data."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform

import numpy as np
import pandas as pd

from cleanup_sim.statistics import bootstrap_ci
from cleanup_sim_v2.layer1 import adaptive_policy_shares
from cleanup_sim_v2.layer1_validation import ExpectedMatrix, validate_summary


SERIES = (
    ("trace_before", "colleague_adaptive_trace_3000_2026-08-29", "layer1_postfix_adaptive_trace_2026-08-22"),
    ("baseline_before", "colleague_baseline_3000_5seed_2026-08-29", "layer1_postfix_path_budget_baseline_2026-08-22"),
    ("trace_after", "colleague_adaptive_trace_3000_AFTERFIX_2026-08-29", "layer1_postfix_adaptive_trace_2026-08-22"),
    ("ablation_smoke", "colleague_adaptive_revision_smoke_2026-08-29", "layer1_postfix_path_budget_baseline_2026-08-22"),
    ("diagnostic_10seed", "colleague_adaptive_revision_10seed_2026-08-29", "layer1_postfix_path_budget_baseline_2026-08-22"),
    ("heavy_calibration", "layer1_postfix_heavy_2026-08-22", "layer1_postfix_budget_calibration_2026-08-22"),
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--control-dir", type=Path, help="Optional local trace plus pr_planner_control repeat.")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    inventory = []
    frames = {}
    policy_frames = []
    for name, parent, child in SERIES:
        directory = repo / "out" / "cleanup_sim_v2" / parent / child
        summary_path = directory / "summary.csv"
        manifest_path = directory / "run_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        summary = pd.read_csv(summary_path)
        frames[name] = summary
        expected = ExpectedMatrix(
            tuple(manifest["budgets"]), tuple(manifest["scenarios"]), tuple(manifest["modes"]),
            manifest["profile"], manifest["seed_start"], manifest["seeds"],
        )
        inputs = [summary_path, manifest_path]
        shares_path = directory / "adaptive_policy_shares.csv"
        if shares_path.exists():
            inputs.append(shares_path)
            shares = pd.read_csv(shares_path)
            # Absent policies are zeros within a run, not missing observations
            # that should disappear from the denominator when averaging seeds.
            wide = shares.pivot(index=["scenario", "seed"], columns="adaptive_selected_policy", values="share").fillna(0.0)
            if not np.allclose(wide.sum(axis=1), 1.0):
                raise ValueError(f"Policy shares do not sum to one: {shares_path}")
            means = wide.groupby(level="scenario").mean().reset_index()
            means.insert(0, "series", name)
            means.insert(1, "share_basis", "all_goal_legs_legacy")
            policy_frames.append(means)
        inventory.append({
            "series": name,
            "directory": directory.relative_to(repo).as_posix(),
            "rows": len(summary),
            "expected_rows": expected.expected_count,
            "seeds": sorted(int(seed) for seed in summary.seed.unique()),
            "stop_reasons": summary.stop_reason.value_counts().to_dict(),
            "manifest": manifest,
            "validation_issues": [asdict(issue) for issue in validate_summary(summary, expected=expected)],
            "sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs},
        })

    diagnostic = frames["diagnostic_10seed"]
    rows = []
    for scenario, group in diagnostic.groupby("scenario"):
        for metric in ("auc_collected_by_path", "collected_ratio"):
            pairs = group.pivot(index="seed", columns="mode", values=metric)
            diff = (pairs["adaptive_mission"] - pairs["belief_horizon"]).to_numpy()
            if len(diff) != 10 or not np.isfinite(diff).all():
                raise ValueError(f"Incomplete paired comparison: {scenario}/{metric}")
            low, high = bootstrap_ci(diff, seed=20260905, n=20000)
            rows.append({
                "scenario": scenario, "metric": metric, "paired_n": len(diff),
                "adaptive_mean": pairs["adaptive_mission"].mean(),
                "belief_horizon_mean": pairs["belief_horizon"].mean(),
                "mean_difference": diff.mean(), "std_difference": diff.std(ddof=1),
                "descriptive_bootstrap_low": low, "descriptive_bootstrap_high": high,
                "wins": int((diff > 1e-12).sum()), "ties": int((np.abs(diff) <= 1e-12).sum()),
                "losses": int((diff < -1e-12).sum()),
            })
    output = args.out_dir
    output.mkdir(parents=True, exist_ok=True)
    payload = {
        "purpose": "Retrospective diagnostic audit; not a confirmatory test or noninferiority claim.",
        "bootstrap": {"seed": 20260905, "resamples": 20000, "alpha": 0.05, "multiple_comparison_adjusted": False},
        "analysis_environment_not_original_run_environment": {
            "python": platform.python_version(),
            **{name: version(name) for name in ("numpy", "pandas", "scipy", "matplotlib", "pytest")},
        },
        "series": inventory,
    }
    (output / "inventory.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pd.DataFrame(rows).to_csv(output / "paired_adaptive_vs_horizon.csv", index=False)
    pd.concat(policy_frames, ignore_index=True).to_csv(output / "legacy_policy_execution_shares.csv", index=False)
    diagnostic.groupby(["scenario", "mode"])[["auc_collected_by_path", "collected_ratio"]].mean().to_csv(output / "diagnostic_means.csv")
    if args.control_dir is not None:
        prefix = "strong_drift__adaptive_mission__nominal__seed300"
        current_path = args.control_dir / f"{prefix}_summary.json"
        committed_path = args.control_dir / "pr_planner_control" / f"{prefix}_summary.json"
        current = json.loads(current_path.read_text(encoding="utf-8"))
        committed = json.loads(committed_path.read_text(encoding="utf-8"))
        physical_keys = current.keys() - {"runner", "git_commit", "git_dirty", "config_hash"}
        equal_summary = all(current[key] == committed[key] for key in physical_keys)
        current_series = pd.read_csv(args.control_dir / f"{prefix}_series.csv")
        committed_series = pd.read_csv(args.control_dir / "pr_planner_control" / f"{prefix}_series.csv")
        reference = frames["trace_after"]
        reference = reference[(reference.scenario == "strong_drift") & (reference.seed == 300)].iloc[0]
        fields = ["config_hash", "collected", "auc_collected_by_path", "path_length_m", "sim_time_s"]
        control = {
            "purpose": "Single-row provenance check; no performance claim.",
            "source_planner_commit": "7e0afb8",
            "committed_planner_loaded_in_memory_before_simulation_import": True,
            "local_physical_summary_equal": equal_summary,
            "local_series_equal": current_series.equals(committed_series),
            "colleague_row": json.loads(reference[fields].to_json()),
            "current_row": {key: current[key] for key in fields},
            "committed_planner_row": {key: committed[key] for key in fields},
            "environment": payload["analysis_environment_not_original_run_environment"],
            "input_sha256": {
                str(path.relative_to(args.control_dir)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (current_path, committed_path, args.control_dir / f"{prefix}_events.csv")
            },
        }
        (output / "local_control.json").write_text(json.dumps(control, indent=2) + "\n", encoding="utf-8")
        shares = adaptive_policy_shares([args.control_dir])
        shares[shares.share_basis == "selector_invocations"].to_csv(output / "local_selector_shares.csv", index=False)
    print(f"Audited {len(inventory)} series; wrote derived evidence to {output}")


if __name__ == "__main__":
    main()
