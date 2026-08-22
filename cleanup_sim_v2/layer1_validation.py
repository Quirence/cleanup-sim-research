from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from itertools import product
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .layer1 import ORACLE_MODE


KEY_COLUMNS = ("path_budget_m", "scenario", "profile", "mode", "seed")
SUMMARY_REQUIRED_COLUMNS = (
    *KEY_COLUMNS,
    "stop_reason",
    "collected",
    "collected_ratio",
    "auc_collected_by_path",
    "path_length_m",
    "sim_time_s",
    "successful_captures",
    "capture_contacts",
    "empty_goal_arrivals",
    "wasted_path_ratio",
)


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    check: str
    message: str
    count: int = 0
    sample: str = ""


@dataclass(frozen=True)
class ExpectedMatrix:
    budgets: tuple[float, ...]
    scenarios: tuple[str, ...]
    modes: tuple[str, ...]
    profile: str
    seed_start: int
    seeds: int

    @property
    def seed_values(self) -> tuple[int, ...]:
        return tuple(range(self.seed_start, self.seed_start + self.seeds))

    @property
    def expected_count(self) -> int:
        return len(self.budgets) * len(self.scenarios) * len(self.modes) * len(self.seed_values)

    def to_frame(self) -> pd.DataFrame:
        rows = [
            {
                "path_budget_m": float(budget),
                "scenario": scenario,
                "profile": self.profile,
                "mode": mode,
                "seed": int(seed),
            }
            for budget, scenario, mode, seed in product(
                self.budgets,
                self.scenarios,
                self.modes,
                self.seed_values,
            )
        ]
        return pd.DataFrame(rows)


def has_failing_issues(issues: Iterable[ValidationIssue], fail_on: str = "major") -> bool:
    order = {"info": 0, "warning": 1, "major": 2, "blocker": 3}
    threshold = order[fail_on.lower()]
    return any(order.get(issue.severity.lower(), 0) >= threshold for issue in issues)


def _sample(df: pd.DataFrame, columns: Iterable[str], limit: int = 5) -> str:
    cols = [column for column in columns if column in df.columns]
    if df.empty or not cols:
        return ""
    return df[cols].head(limit).to_json(orient="records", force_ascii=False)


def _issue(severity: str, check: str, message: str, df: pd.DataFrame | None = None) -> ValidationIssue:
    count = 0 if df is None else int(len(df))
    sample = "" if df is None else _sample(df, KEY_COLUMNS + ("collected_ratio", "auc_collected_by_path", "stop_reason"))
    return ValidationIssue(severity, check, message, count, sample)


def _bounds_issue(df: pd.DataFrame, column: str, low: float, high: float) -> ValidationIssue | None:
    if column not in df.columns:
        return None
    mask = (df[column] < low - 1e-12) | (df[column] > high + 1e-12)
    if not bool(mask.any()):
        return None
    return _issue("blocker", f"{column}_bounds", f"`{column}` must be in [{low}, {high}].", df[mask])


def validate_summary(
    summary: pd.DataFrame,
    *,
    expected: ExpectedMatrix | None = None,
    max_time_budget_rate: float = 0.05,
    path_tolerance_m: float = 5.0,
    max_adaptive_equal_share: float = 0.80,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if summary.empty:
        return [ValidationIssue("blocker", "empty_summary", "Summary is empty.")]

    missing_columns = [column for column in SUMMARY_REQUIRED_COLUMNS if column not in summary.columns]
    if missing_columns:
        issues.append(
            ValidationIssue(
                "blocker",
                "missing_columns",
                "Summary is missing required columns: " + ", ".join(missing_columns),
                len(missing_columns),
            )
        )
        return issues

    key_nulls = summary[list(KEY_COLUMNS)].isna().any(axis=1)
    if bool(key_nulls.any()):
        issues.append(_issue("blocker", "null_keys", "Key columns must not contain null values.", summary[key_nulls]))

    duplicate_mask = summary.duplicated(list(KEY_COLUMNS), keep=False)
    if bool(duplicate_mask.any()):
        issues.append(
            _issue("blocker", "duplicate_runs", "Duplicate rows for the same budget/scenario/profile/mode/seed.", summary[duplicate_mask])
        )

    if expected is not None:
        expected_df = expected.to_frame()
        actual_keys = summary[list(KEY_COLUMNS)].copy()
        actual_keys["path_budget_m"] = actual_keys["path_budget_m"].astype(float)
        actual_keys["seed"] = actual_keys["seed"].astype(int)
        merged_missing = expected_df.merge(actual_keys.drop_duplicates(), on=list(KEY_COLUMNS), how="left", indicator=True)
        missing = merged_missing[merged_missing["_merge"] == "left_only"].drop(columns="_merge")
        if not missing.empty:
            issues.append(
                _issue(
                    "blocker",
                    "missing_expected_runs",
                    f"Missing expected runs: {len(missing)} of {expected.expected_count}.",
                    missing,
                )
            )
        merged_unknown = actual_keys.drop_duplicates().merge(expected_df, on=list(KEY_COLUMNS), how="left", indicator=True)
        unknown = merged_unknown[merged_unknown["_merge"] == "left_only"].drop(columns="_merge")
        if not unknown.empty:
            issues.append(_issue("major", "unexpected_runs", "Summary contains rows outside the expected matrix.", unknown))

    for column in ("collected_ratio", "auc_collected_by_path", "wasted_path_ratio", "goal_success_rate"):
        bounds = _bounds_issue(summary, column, 0.0, 1.0)
        if bounds is not None:
            issues.append(bounds)

    auc_too_high = summary["auc_collected_by_path"] > summary["collected_ratio"] + 1e-9
    if bool(auc_too_high.any()):
        issues.append(_issue("blocker", "auc_exceeds_final_collection", "AUC by path cannot exceed final collected ratio.", summary[auc_too_high]))

    done_not_full = (summary["stop_reason"] == "done") & (summary["collected_ratio"] < 1.0 - 1e-12)
    if bool(done_not_full.any()):
        issues.append(_issue("blocker", "done_not_full", "`done` stop reason requires all debris to be collected.", summary[done_not_full]))

    full_not_done = (summary["collected_ratio"] >= 1.0 - 1e-12) & (summary["stop_reason"] != "done")
    if bool(full_not_done.any()):
        issues.append(_issue("blocker", "full_not_done", "Full collection must stop with `done`.", summary[full_not_done]))

    over_budget = summary["path_length_m"] > summary["path_budget_m"] + path_tolerance_m
    if bool(over_budget.any()):
        issues.append(_issue("major", "path_exceeds_budget", "Path length exceeds the configured budget tolerance.", summary[over_budget]))

    under_budget_stop = (summary["stop_reason"] == "path_budget") & (
        summary["path_length_m"] < summary["path_budget_m"] - max(10.0, path_tolerance_m)
    )
    if bool(under_budget_stop.any()):
        issues.append(
            _issue("major", "path_budget_stop_too_early", "`path_budget` stop occurred well below the path budget.", summary[under_budget_stop])
        )

    non_oracle = summary[summary["mode"] != ORACLE_MODE]
    time_budget_rate = float((non_oracle["stop_reason"] == "time_budget").mean()) if not non_oracle.empty else 0.0
    if time_budget_rate > max_time_budget_rate:
        time_budget_rows = non_oracle[non_oracle["stop_reason"] == "time_budget"]
        issues.append(
            _issue(
                "blocker",
                "time_budget_rate",
                f"Non-oracle time-budget rate {time_budget_rate:.3f} exceeds {max_time_budget_rate:.3f}.",
                time_budget_rows,
            )
        )

    capture_mismatch = summary["successful_captures"] != summary["collected"]
    if bool(capture_mismatch.any()):
        issues.append(
            _issue("blocker", "successful_capture_mismatch", "`successful_captures` must equal collected count.", summary[capture_mismatch])
        )

    contact_mismatch = summary["capture_contacts"] < summary["successful_captures"]
    if bool(contact_mismatch.any()):
        issues.append(
            _issue("blocker", "capture_contacts_lt_successes", "`capture_contacts` cannot be less than successes.", summary[contact_mismatch])
        )

    if "git_commit" in summary.columns:
        unknown_commit = summary["git_commit"].astype(str).eq("unknown")
        if bool(unknown_commit.any()):
            issues.append(_issue("major", "unknown_git_commit", "Rows with unknown git commit cannot support reproducibility.", summary[unknown_commit]))
        commit_count = summary["git_commit"].dropna().astype(str).nunique()
        if commit_count > 1:
            issues.append(ValidationIssue("major", "mixed_git_commits", f"Summary contains {commit_count} git commits."))
    if "git_dirty" in summary.columns:
        dirty = summary["git_dirty"].astype(str).str.lower().isin({"true", "1"})
        if bool(dirty.any()):
            issues.append(_issue("major", "dirty_git_state", "Rows were produced from a dirty tracked worktree.", summary[dirty]))

    for column in ("detection_precision", "detection_recall", "collection_precision"):
        bounds = _bounds_issue(summary, column, 0.0, 1.0)
        if bounds is not None:
            issues.append(bounds)

    if ORACLE_MODE in set(summary["mode"]):
        keys = ["path_budget_m", "scenario", "profile", "seed"]
        oracle = summary[summary["mode"] == ORACLE_MODE][keys + ["collected_ratio", "auc_collected_by_path"]].rename(
            columns={
                "collected_ratio": "oracle_collected_ratio_check",
                "auc_collected_by_path": "oracle_auc_check",
            }
        )
        merged = summary.merge(oracle, on=keys, how="left")
        missing_oracle = merged[merged["oracle_collected_ratio_check"].isna()]
        if not missing_oracle.empty:
            issues.append(_issue("blocker", "missing_oracle_pairs", "Oracle row is missing for some budget/scenario/seed.", missing_oracle))
        worse_collected = (merged["mode"] != ORACLE_MODE) & (
            merged["oracle_collected_ratio_check"] + 1e-9 < merged["collected_ratio"]
        )
        if bool(worse_collected.any()):
            issues.append(_issue("blocker", "oracle_collected_worse", "Oracle collected less than a non-oracle row.", merged[worse_collected]))
        worse_auc = (merged["mode"] != ORACLE_MODE) & (merged["oracle_auc_check"] + 1e-9 < merged["auc_collected_by_path"])
        if bool(worse_auc.any()):
            issues.append(_issue("blocker", "oracle_auc_worse", "Oracle AUC is lower than a non-oracle row.", merged[worse_auc]))

    for column in ("regret_to_best_fixed_auc", "regret_to_best_fixed_collected_ratio"):
        if column in summary.columns:
            negative = summary[column].dropna() < -1e-12
            if bool(negative.any()):
                rows = summary.loc[negative.index[negative]]
                issues.append(_issue("major", f"{column}_negative", f"`{column}` must be non-negative.", rows))
            oracle_regret = summary.loc[summary["mode"] == ORACLE_MODE, column]
            if len(oracle_regret) and oracle_regret.notna().any():
                issues.append(_issue("major", f"{column}_oracle_not_nan", f"`{column}` must be NaN for oracle rows.", summary[summary["mode"] == ORACLE_MODE]))

    near_zero = summary[(summary["mode"] != ORACLE_MODE) & (summary["collected"] <= 1)]
    if not near_zero.empty:
        issues.append(_issue("warning", "near_zero_collection", "Non-oracle rows collected at most one object; inspect before interpretation.", near_zero))

    if {"adaptive_mission", "belief_horizon"}.issubset(set(summary["mode"])):
        adaptive = summary[summary["mode"].isin({"adaptive_mission", "belief_horizon"})]
        pivot = adaptive.pivot_table(
            index=["path_budget_m", "scenario", "profile", "seed"],
            columns="mode",
            values=["collected_ratio", "auc_collected_by_path"],
            aggfunc="first",
        )
        if ("collected_ratio", "adaptive_mission") in pivot.columns and ("collected_ratio", "belief_horizon") in pivot.columns:
            equal = (
                np.isclose(pivot[("collected_ratio", "adaptive_mission")], pivot[("collected_ratio", "belief_horizon")])
                & np.isclose(pivot[("auc_collected_by_path", "adaptive_mission")], pivot[("auc_collected_by_path", "belief_horizon")])
            )
            share = float(equal.mean()) if len(equal) else 0.0
            if share > max_adaptive_equal_share:
                issues.append(
                    ValidationIssue(
                        "warning",
                        "adaptive_matches_belief_horizon",
                        f"`adaptive_mission` equals `belief_horizon` in {share:.1%} paired cells.",
                        int(equal.sum()),
                    )
                )

    return issues


def issues_to_frame(issues: Iterable[ValidationIssue]) -> pd.DataFrame:
    return pd.DataFrame([asdict(issue) for issue in issues])


def validation_summary(issues: Iterable[ValidationIssue]) -> dict:
    issue_list = list(issues)
    by_severity: dict[str, int] = {}
    for issue in issue_list:
        by_severity[issue.severity] = by_severity.get(issue.severity, 0) + 1
    return {
        "issue_count": len(issue_list),
        "by_severity": by_severity,
        "has_major_or_blocker": has_failing_issues(issue_list, "major"),
        "has_blocker": has_failing_issues(issue_list, "blocker"),
    }


def write_validation_outputs(out_dir: Path, issues: list[ValidationIssue]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    issues_to_frame(issues).to_csv(out_dir / "validation_issues.csv", index=False)
    (out_dir / "validation_summary.json").write_text(
        json.dumps(validation_summary(issues), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
