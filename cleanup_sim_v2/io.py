from __future__ import annotations

import json
import hashlib
import subprocess
from pathlib import Path

import numpy as np

from .simulation import RunResult


def config_hash(config_dict: dict) -> str:
    payload = json.dumps(config_dict, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def git_dirty(include_untracked: bool = False) -> bool:
    command = ["git", "status", "--short"]
    if not include_untracked:
        command.append("--untracked-files=no")
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return True
    return bool(result.stdout.strip())


def save_run(result: RunResult, out_dir: Path, prefix: str) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg_dict = result.config.to_dict()
    manifest = {
        "config_hash": config_hash(cfg_dict),
        "git_commit": git_commit(),
        "git_dirty": git_dirty(),
        "config": cfg_dict,
        "summary": result.summary,
    }
    paths = {
        "summary": out_dir / f"{prefix}_summary.json",
        "series": out_dir / f"{prefix}_series.csv",
        "events": out_dir / f"{prefix}_events.csv",
        "density": out_dir / f"{prefix}_density.npy",
        "positions": out_dir / f"{prefix}_positions.npy",
        "config": out_dir / f"{prefix}_config.json",
        "manifest": out_dir / f"{prefix}_manifest.json",
    }
    paths["summary"].write_text(json.dumps(result.summary, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["config"].write_text(json.dumps(cfg_dict, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["manifest"].write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    result.series.to_csv(paths["series"], index=False)
    result.events.to_csv(paths["events"], index=False)
    np.save(paths["density"], result.density_map.expected_count)
    np.save(paths["positions"], result.field.positions)
    return paths
