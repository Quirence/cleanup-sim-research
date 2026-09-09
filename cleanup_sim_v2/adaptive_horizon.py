"""Analysis helpers for the bounded adaptive execution-horizon experiment."""

from __future__ import annotations

import math
import zlib

import numpy as np
import pandas as pd

from cleanup_sim.statistics import bootstrap_ci


HORIZON_VARIANTS = {
    "queue_commit": False,
    "replan_each_leg": True,
}

EFFECT_METRICS = (
    "collected_ratio",
    "remaining_count",
    "complete_cleanup",
    "auc_collected_by_path",
    "wasted_path_ratio",
    "empty_goal_arrivals_per_km",
    "goal_success_rate",
    "sim_time_s",
    "selector_invocations",
    "route_continuations",
    "queue_discarded_points",
)

# These diagnostics are computed from goal_started regime snapshots.  They are
# optional so summaries produced by the preregistered pilot commit remain valid.
QUEUE_DIAGNOSTIC_METRICS = (
    "queued_route_assignment_fraction",
    "route_staleness_ratio_mean",
    "route_staleness_ratio_exceedance_fraction",
)


def summarize_horizon_events(events: pd.DataFrame) -> dict[str, float | int]:
    """Summarize execution-horizon counters and committed-route exposure."""
    starts = events.loc[events["event"] == "goal_started"]
    completed = events.loc[events["event"] == "goal_completed"]

    def total(frame: pd.DataFrame, column: str) -> int:
        if column not in frame:
            return 0
        return int(pd.to_numeric(frame[column], errors="coerce").fillna(0).sum())

    result: dict[str, float | int] = {
        "selector_invocations": total(starts, "adaptive_selector_invoked"),
        "route_continuations": total(starts, "adaptive_route_continuation"),
        "queue_discarded_points": total(completed, "adaptive_queue_discarded_points"),
    }
    if starts.empty or not {
        "regime_queued_route_points",
        "regime_route_staleness_ratio",
    }.issubset(starts.columns):
        result.update({
            "regime_route_snapshot_coverage": math.nan,
            "queued_route_assignment_fraction": math.nan,
            "route_staleness_ratio_mean": math.nan,
            "route_staleness_ratio_exceedance_fraction": math.nan,
            "queued_route_staleness_ratio_mean": math.nan,
        })
        return result

    points = pd.to_numeric(starts["regime_queued_route_points"], errors="coerce")
    staleness = pd.to_numeric(starts["regime_route_staleness_ratio"], errors="coerce")
    valid = points.notna() & staleness.notna()
    queued = valid & points.gt(0)
    valid_count = int(valid.sum())
    queued_count = int(queued.sum())
    result.update({
        "regime_route_snapshot_coverage": valid_count / len(starts),
        "queued_route_assignment_fraction": queued_count / valid_count if valid_count else math.nan,
        "route_staleness_ratio_mean": float(staleness.loc[valid].mean()) if valid_count else math.nan,
        "route_staleness_ratio_exceedance_fraction": (
            float(staleness.loc[valid].gt(1.0).mean()) if valid_count else math.nan
        ),
        "queued_route_staleness_ratio_mean": (
            float(staleness.loc[queued].mean()) if queued_count else math.nan
        ),
    })
    return result


def _analysis_seed(scope: str, metric: str) -> int:
    return int(zlib.crc32(f"adaptive-horizon|{scope}|{metric}".encode("utf-8")) & 0xFFFFFFFF)


def validate_horizon_matrix(summary: pd.DataFrame) -> None:
    required = {"scenario", "seed", "horizon_variant", "initial_debris_count", *EFFECT_METRICS}
    missing = sorted(required - set(summary.columns))
    if missing:
        raise ValueError(f"Missing horizon summary columns: {missing}")
    expected_variants = set(HORIZON_VARIANTS)
    actual_variants = set(summary["horizon_variant"].dropna())
    if actual_variants != expected_variants:
        raise ValueError(f"Expected horizon variants {sorted(expected_variants)}, got {sorted(actual_variants)}")
    counts = summary.groupby(["scenario", "seed", "horizon_variant"], dropna=False).size()
    if not (counts == 1).all():
        raise ValueError("Horizon matrix has duplicate scenario/seed/variant rows")
    coverage = summary.groupby(["scenario", "seed"], dropna=False)["horizon_variant"].nunique()
    if not (coverage == len(expected_variants)).all():
        raise ValueError("Horizon matrix has unpaired scenario/seed rows")


def _paired(summary: pd.DataFrame, metric: str) -> pd.DataFrame:
    return summary.pivot(index=["scenario", "seed"], columns="horizon_variant", values=metric).reset_index()


def analyze_horizon_results(summary: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    validate_horizon_matrix(summary)
    rows: list[dict] = []

    optional_metrics = tuple(metric for metric in QUEUE_DIAGNOSTIC_METRICS if metric in summary)
    for metric in optional_metrics:
        if summary[metric].isna().any():
            raise ValueError(f"Optional horizon metric is incomplete: {metric}")

    for metric in (*EFFECT_METRICS, *optional_metrics):
        paired = _paired(summary, metric).dropna(subset=list(HORIZON_VARIANTS))
        for scenario in sorted(paired["scenario"].unique()):
            block = paired[paired["scenario"] == scenario]
            differences = (block["replan_each_leg"] - block["queue_commit"]).to_numpy(dtype=float)
            ci_low, ci_high = bootstrap_ci(
                differences,
                seed=_analysis_seed(str(scenario), metric),
                n=20_000,
            )
            rows.append({
                "scope": "scenario",
                "scenario": scenario,
                "metric": metric,
                "paired_runs": int(len(block)),
                "queue_commit_mean": float(block["queue_commit"].mean()),
                "replan_each_leg_mean": float(block["replan_each_leg"].mean()),
                "mean_difference_replan_minus_queue": float(np.mean(differences)),
                "ci95_low": ci_low,
                "ci95_high": ci_high,
                "positive_pairs": int(np.sum(differences > 1e-12)),
                "tied_pairs": int(np.sum(np.abs(differences) <= 1e-12)),
                "negative_pairs": int(np.sum(differences < -1e-12)),
            })

        # Scenarios are repeated conditions for a seed. Average within seed
        # before bootstrapping so the seed, rather than a scenario row, remains
        # the independent block in the equal-weight overall result.
        by_seed = paired.groupby("seed")[["queue_commit", "replan_each_leg"]].mean()
        differences = (by_seed["replan_each_leg"] - by_seed["queue_commit"]).to_numpy(dtype=float)
        ci_low, ci_high = bootstrap_ci(
            differences,
            seed=_analysis_seed("equal_weight_over_scenarios", metric),
            n=20_000,
        )
        rows.append({
            "scope": "equal_weight_over_scenarios",
            "scenario": "ALL",
            "metric": metric,
            "paired_runs": int(len(by_seed)),
            "queue_commit_mean": float(by_seed["queue_commit"].mean()),
            "replan_each_leg_mean": float(by_seed["replan_each_leg"].mean()),
            "mean_difference_replan_minus_queue": float(np.mean(differences)),
            "ci95_low": ci_low,
            "ci95_high": ci_high,
            "positive_pairs": int(np.sum(differences > 1e-12)),
            "tied_pairs": int(np.sum(np.abs(differences) <= 1e-12)),
            "negative_pairs": int(np.sum(differences < -1e-12)),
        })

    effects = pd.DataFrame(rows)
    primary = effects[
        (effects["metric"] == "collected_ratio")
        & (effects["scope"] == "equal_weight_over_scenarios")
    ].iloc[0]
    per_scenario = effects[
        (effects["metric"] == "collected_ratio")
        & (effects["scope"] == "scenario")
    ]
    debris_counts = summary["initial_debris_count"].dropna().astype(int).unique()
    if len(debris_counts) != 1 or debris_counts[0] <= 0:
        raise ValueError("The decision rule requires one positive initial debris count")
    one_object_ratio = 1.0 / float(debris_counts[0])
    mean_difference = float(primary["mean_difference_replan_minus_queue"])
    ci_low = float(primary["ci95_low"])
    ci_high = float(primary["ci95_high"])
    scenario_differences = per_scenario["mean_difference_replan_minus_queue"].to_numpy(dtype=float)

    clear_replan = (
        mean_difference >= one_object_ratio
        and ci_low > 0.0
        and np.all(scenario_differences > -one_object_ratio)
    )
    clear_queue = (
        mean_difference <= -one_object_ratio
        and ci_high < 0.0
        and np.all(scenario_differences < one_object_ratio)
    )
    if clear_replan:
        decision = "replan_each_leg"
        rationale = "clear_primary_advantage"
    elif clear_queue:
        decision = "queue_commit"
        rationale = "clear_primary_advantage"
    else:
        decision = "ambiguous"
        rationale = "primary_effect_uncertain_small_or_scenario_dependent"

    report = {
        "comparison": "replan_each_leg_minus_queue_commit",
        "primary_metric": "collected_ratio_at_common_path_budget",
        "secondary_completion_metrics": ["remaining_count", "complete_cleanup"],
        "one_object_ratio": one_object_ratio,
        "decision": decision,
        "decision_rationale": rationale,
        "decision_rule": {
            "minimum_mean_effect": "one initial debris object",
            "overall_ci_must_exclude_zero": True,
            "no_scenario_mean_loss_at_least_one_object": True,
        },
        "overall_primary_effect": {
            key: (int(primary[key]) if key.endswith("pairs") or key == "paired_runs" else float(primary[key]))
            for key in (
                "paired_runs",
                "queue_commit_mean",
                "replan_each_leg_mean",
                "mean_difference_replan_minus_queue",
                "ci95_low",
                "ci95_high",
                "positive_pairs",
                "tied_pairs",
                "negative_pairs",
            )
        },
        "scenario_primary_effects": per_scenario[
            ["scenario", "paired_runs", "mean_difference_replan_minus_queue", "ci95_low", "ci95_high"]
        ].to_dict("records"),
        "interpretation_note": (
            "AUC and efficiency diagnostics are secondary and cannot overturn a clear final-collection result. "
            "An ambiguous result requires a documented user decision before changing the default horizon."
        ),
    }
    if not math.isfinite(mean_difference):
        raise ValueError("Primary horizon effect is not finite")
    return effects, report
