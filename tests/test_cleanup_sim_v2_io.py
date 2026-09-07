from __future__ import annotations

import json
import os
import re
from dataclasses import replace
from pathlib import Path

from cleanup_sim_v2.config import WorldConfig, scenario_config
from cleanup_sim_v2.io import config_hash, git_commit, git_dirty, save_run
from cleanup_sim_v2.simulation import run_simulation
from cleanup_sim_v2.provenance import file_sha256


def test_git_commit_returns_a_short_hash_inside_this_repository() -> None:
    commit = git_commit()
    assert commit != "unknown"
    assert re.fullmatch(r"[0-9a-f]{4,40}", commit)


def test_git_dirty_returns_a_bool_inside_this_repository() -> None:
    assert isinstance(git_dirty(), bool)


def test_git_commit_falls_back_to_unknown_outside_a_git_repository(tmp_path: Path) -> None:
    # subprocess.run's "git rev-parse" has no repo to inspect from a plain tmp
    # directory, which is exactly the OSError/CalledProcessError path git_commit
    # is meant to degrade gracefully from - exercised for real, not mocked.
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        assert git_commit() == "unknown"
    finally:
        os.chdir(original_cwd)


def test_git_dirty_falls_back_to_true_outside_a_git_repository(tmp_path: Path) -> None:
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        assert git_dirty() is True
    finally:
        os.chdir(original_cwd)


def test_save_run_writes_all_expected_files_with_matching_content(tmp_path: Path) -> None:
    cfg = scenario_config("static_calm", 0, "greedy")
    cfg = replace(
        cfg,
        world=WorldConfig(width_m=80.0, height_m=80.0, depot_x_m=5.0, depot_y_m=5.0, n_debris=2),
        platform=replace(cfg.platform, max_path_m=50.0, tmax_s=100.0),
    )
    result = run_simulation(cfg)

    paths = save_run(result, tmp_path, "probe")

    assert set(paths) == {"summary", "series", "events", "density", "positions", "config", "manifest"}
    for path in paths.values():
        assert path.exists()

    saved_summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    assert saved_summary == result.summary

    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["config_hash"] == config_hash(result.config.to_dict())
    assert manifest["summary"] == result.summary
    assert manifest["config"] == result.config.to_dict()
    assert manifest["provenance_capture"] == "save_time"
    assert manifest["provenance"]["environment"]["python"]
    for kind, artifact in manifest["artifacts"].items():
        assert artifact["sha256"] == file_sha256(paths[kind])


def test_save_run_creates_the_output_directory_if_missing(tmp_path: Path) -> None:
    cfg = scenario_config("static_calm", 0, "greedy")
    cfg = replace(
        cfg,
        world=WorldConfig(width_m=80.0, height_m=80.0, depot_x_m=5.0, depot_y_m=5.0, n_debris=2),
        platform=replace(cfg.platform, max_path_m=50.0, tmax_s=100.0),
    )
    result = run_simulation(cfg)
    nested_out_dir = tmp_path / "a" / "b" / "c"
    assert not nested_out_dir.exists()

    save_run(result, nested_out_dir, "probe")

    assert nested_out_dir.exists()
