from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys

import pytest

from cleanup_sim_v2 import run_experiments, run_layer1
from cleanup_sim_v2.config import scenario_config
from cleanup_sim_v2.io import save_run
from cleanup_sim_v2.provenance import (
    capture_provenance, file_sha256, source_snapshot, validate_resume_configs, validate_resume_provenance,
)
from cleanup_sim_v2.reproducibility import compare_run_manifests, first_csv_difference
from cleanup_sim_v2.simulation import run_simulation


def test_environment_snapshot_records_runtime_and_numpy_build() -> None:
    provenance = capture_provenance()
    environment = provenance["environment"]
    assert environment["python"] == sys.version
    assert environment["executable"] == sys.executable
    assert {"numpy", "pandas", "scipy", "matplotlib", "pytest"} <= {
        name.lower() for name in environment["packages"]
    }
    assert environment["numpy_build"]
    assert environment["rng"] == "PCG64"
    assert len(provenance["git_commit_full"]) == 40
    assert "cleanup_sim_v2/planners.py" in provenance["source"]["files"]


def test_source_snapshot_detects_untracked_source_edits_but_ignores_outputs(tmp_path: Path) -> None:
    package = tmp_path / "cleanup_sim_v2"
    package.mkdir()
    source = package / "planner.py"
    source.write_text("threshold = 0.6\n", encoding="utf-8")
    before = source_snapshot(tmp_path)
    (tmp_path / "out").mkdir()
    (tmp_path / "out/summary.csv").write_text("collected\n143\n", encoding="utf-8")
    assert source_snapshot(tmp_path) == before
    source.write_text("threshold = 1.0\n", encoding="utf-8")
    assert source_snapshot(tmp_path)["sha256"] != before["sha256"]


@pytest.mark.parametrize("row", [{}, {"provenance_id": "different"}])
def test_resume_rejects_unknown_or_different_execution_identity(row: dict) -> None:
    with pytest.raises(ValueError, match="Checkpoint"):
        validate_resume_provenance([row], {"provenance_id": "current"})


@pytest.mark.parametrize("rows", [
    [{"seed": 300, "config_hash": "changed"}],
    [{"seed": 301, "config_hash": "expected"}],
    [{"seed": 300, "config_hash": "expected"}] * 2,
])
def test_resume_preflight_rejects_changed_config_outside_matrix_or_duplicate(rows: list[dict]) -> None:
    with pytest.raises(ValueError, match="configuration/matrix"):
        validate_resume_configs(rows, {(300,): "expected"}, ("seed",))


def test_first_csv_difference_reports_event_context_and_extra_rows(tmp_path: Path) -> None:
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    a.write_text("time_s,event,x\n1,goal_started,2\n2,capture,3\n", encoding="utf-8")
    b.write_text("time_s,event,x\n1,goal_started,2\n2,capture,4\n", encoding="utf-8")
    difference = first_csv_difference(a, b)
    assert difference["csv_line"] == 3
    assert difference["column"] == "x"
    assert difference["left_context"]["event"] == "capture"
    b.write_text(a.read_text(encoding="utf-8") + "3,capture,4\n", encoding="utf-8")
    assert first_csv_difference(a, b)["kind"] == "row_count"


@pytest.fixture
def saved_pair(tmp_path: Path) -> tuple[Path, Path]:
    cfg = scenario_config("strong_drift", 300, "adaptive_mission")
    cfg = replace(cfg, platform=replace(cfg.platform, max_path_m=20.0, tmax_s=40.0))
    provenance = capture_provenance()
    # Synthetic clean metadata for a comparison-unit fixture, not evidence.
    provenance["git_dirty"] = False
    result = run_simulation(cfg)
    paths = save_run(result, tmp_path / "a", "probe", provenance=provenance)
    save_run(run_simulation(cfg), tmp_path / "b", "probe", provenance=provenance)
    return paths["manifest"], tmp_path / "b/probe_manifest.json"


def test_compare_requires_exact_intact_artifacts_and_matching_identity(saved_pair: tuple[Path, Path]) -> None:
    left, right = saved_pair
    assert compare_run_manifests(left, right)["passed"]
    manifest = json.loads(right.read_text(encoding="utf-8"))
    manifest["provenance"]["environment_sha256"] = "different"
    right.write_text(json.dumps(manifest), encoding="utf-8")
    comparison = compare_run_manifests(left, right)
    assert not comparison["passed"]
    assert not comparison["same_identity"]


def test_compare_detects_changed_summary_even_when_events_match(saved_pair: tuple[Path, Path]) -> None:
    left, right = saved_pair
    path = right.parent / "probe_summary.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    summary["collected"] += 1
    path.write_text(json.dumps(summary), encoding="utf-8")
    comparison = compare_run_manifests(left, right)
    assert not comparison["passed"]
    assert comparison["artifacts"]["events"]["exact"]
    assert not comparison["artifacts"]["summary"]["integrity_ok"]
    assert "collected" in comparison["artifacts"]["summary"]["different_fields"]


def test_compare_rejects_missing_artifact_and_unknown_provenance(saved_pair: tuple[Path, Path]) -> None:
    left, right = saved_pair
    (right.parent / "probe_events.csv").unlink()
    assert not compare_run_manifests(left, right)["passed"]
    for path in (left, right):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest.pop("provenance")
        path.write_text(json.dumps(manifest), encoding="utf-8")
    comparison = compare_run_manifests(left, right)
    assert not comparison["same_identity"]


def test_run_experiments_resume_rejects_changed_budget_without_overwriting_checkpoint(tmp_path, monkeypatch) -> None:
    args = ["run_experiments", "--seeds", "1", "--scenarios", "static_calm", "--modes", "greedy",
            "--max-path-m", "20", "--tmax-s", "30", "--checkpoint", "--out-dir", str(tmp_path)]
    monkeypatch.setattr(sys, "argv", args)
    run_experiments.main()
    before = file_sha256(tmp_path / "summary_partial.csv")
    changed = list(args)
    changed[changed.index("20")] = "25"
    monkeypatch.setattr(sys, "argv", changed + ["--resume"])
    with pytest.raises(ValueError, match="configuration"):
        run_experiments.main()
    assert file_sha256(tmp_path / "summary_partial.csv") == before


def test_layer1_saves_same_provenance_in_series_and_run_manifest(tmp_path) -> None:
    run_layer1.run_series(
        phase="trace", out_dir=tmp_path, budgets=[20.0], seeds=1, seed_start=300,
        scenarios=["strong_drift"], modes=["adaptive_mission"], profile="nominal",
        save_runs=True, checkpoint=True, resume=False, validate_outputs=False, fail_on="major",
    )
    series = json.loads((tmp_path / "run_manifest.json").read_text(encoding="utf-8"))
    run = json.loads(next((tmp_path / "runs").glob("*_manifest.json")).read_text(encoding="utf-8"))
    assert series["provenance"] == run["provenance"]
    assert run["summary"]["provenance_id"] == series["provenance"]["provenance_id"]
    assert run["provenance_capture"] == "runner_start"
