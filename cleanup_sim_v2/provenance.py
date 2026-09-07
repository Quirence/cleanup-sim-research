"""Recorded execution identity; configuration alone does not identify a run."""

from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
from importlib import metadata
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
THREAD_ENV_VARS = (
    "PYTHONHASHSEED", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
    "NPY_DISABLE_CPU_FEATURES", "MKL_CBWR",
)


def json_sha256(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_snapshot(root: Path = REPO_ROOT) -> dict:
    # Include untracked Python files, runners, analysis code, and dependency
    # declarations. The hash identifies actual bytes, including line endings.
    paths = set()
    for directory in ("cleanup_sim_v2", "scripts"):
        paths.update((root / directory).rglob("*.py"))
    paths.update(root / name for name in (
        "cleanup_sim/__init__.py", "cleanup_sim/statistics.py",
        "pyproject.toml", "requirements.txt",
    ) if (root / name).is_file())
    files = {path.relative_to(root).as_posix(): file_sha256(path) for path in sorted(paths)}
    return {"sha256": json_sha256(files), "files": files}


def environment_snapshot() -> dict:
    stream = io.StringIO()
    with redirect_stdout(stream):
        np.show_config()
    return {
        "python": sys.version,
        "implementation": platform.python_implementation(),
        "executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "byteorder": sys.byteorder,
        "packages": dict(sorted(
            (dist.metadata["Name"], dist.version)
            for dist in metadata.distributions() if dist.metadata["Name"]
        )),
        "numpy_build": stream.getvalue(),
        "rng": type(np.random.default_rng(0).bit_generator).__name__,
        "environment_variables": {name: os.environ.get(name) for name in THREAD_ENV_VARS},
    }


def capture_provenance(root: Path = REPO_ROOT) -> dict:
    def git(*args: str) -> str | None:
        try:
            return subprocess.run(
                ["git", *args], cwd=root, check=True, capture_output=True, text=True,
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None

    commit = git("rev-parse", "HEAD") or "unknown"
    status = git("status", "--porcelain", "--untracked-files=normal")
    source = source_snapshot(root)
    environment = environment_snapshot()
    identity = {
        "git_commit_full": commit,
        "git_dirty": status is None or bool(status),
        "source_sha256": source["sha256"],
        "environment_sha256": json_sha256(environment),
    }
    return {
        "schema_version": 1,
        **identity,
        "provenance_id": json_sha256(identity),
        "source": source,
        "environment": environment,
    }


def summary_provenance(provenance: dict) -> dict:
    return {key: provenance[key] for key in (
        "provenance_id", "git_commit_full", "source_sha256", "environment_sha256",
    )}


def validate_resume_provenance(rows: list[dict], provenance: dict) -> None:
    if any(row.get("provenance_id") != provenance["provenance_id"] for row in rows):
        raise ValueError(
            "Checkpoint has missing or different code/environment provenance. "
            "Use a new output directory; preserve the original checkpoint."
        )


def validate_resume_configs(rows: list[dict], expected: dict[tuple, str], key_fields: tuple[str, ...]) -> None:
    """Validate all retained rows before any simulation or checkpoint write."""
    seen = set()
    for row in rows:
        key = tuple(row[field] for field in key_fields)
        if key in seen or key not in expected or row.get("config_hash") != expected[key]:
            raise ValueError("Checkpoint configuration/matrix changed or has duplicates; use a new output directory.")
        seen.add(key)


def assert_provenance_unchanged(provenance: dict) -> None:
    if capture_provenance()["provenance_id"] != provenance["provenance_id"]:
        raise RuntimeError("Code, Git state, or environment changed during execution; run is not validated.")
