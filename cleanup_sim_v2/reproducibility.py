"""Exact artifact comparison, with the first divergent event/series cell."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .provenance import file_sha256


ARTIFACTS = ("summary", "config", "events", "series", "density", "positions")


def first_csv_difference(left: Path, right: Path) -> dict | None:
    # Compare serialized cells without float parsing or tolerance. CSV line
    # endings may differ; the artifact SHA comparison still rejects that case.
    with left.open(encoding="utf-8", newline="") as stream:
        a = list(csv.reader(stream))
    with right.open(encoding="utf-8", newline="") as stream:
        b = list(csv.reader(stream))
    if not a or not b:
        return None if a == b else {"kind": "empty_file", "left_rows": len(a), "right_rows": len(b)}
    if a[0] != b[0]:
        return {"kind": "columns", "left": a[0], "right": b[0]}
    for row_index, (row_a, row_b) in enumerate(zip(a[1:], b[1:])):
        if len(row_a) != len(row_b):
            return {"kind": "row_width", "row_index": row_index}
        for column_index, (value_a, value_b) in enumerate(zip(row_a, row_b)):
            if value_a != value_b:
                return {
                    "kind": "cell", "row_index": row_index, "csv_line": row_index + 2,
                    "column": a[0][column_index], "left": value_a, "right": value_b,
                    "left_context": dict(zip(a[0], row_a)),
                    "right_context": dict(zip(b[0], row_b)),
                }
    if len(a) != len(b):
        return {"kind": "row_count", "first_unpaired_row_index": min(len(a), len(b)) - 1,
                "left_rows": len(a) - 1, "right_rows": len(b) - 1}
    return None


def compare_run_manifests(left: Path, right: Path) -> dict:
    manifests = [json.loads(path.read_text(encoding="utf-8")) for path in (left, right)]
    identity_fields = ("provenance_id", "git_commit_full", "source_sha256", "environment_sha256")
    same_identity = all(
        manifests[0].get("provenance", {}).get(key) is not None
        and manifests[0]["provenance"][key] == manifests[1].get("provenance", {}).get(key)
        for key in identity_fields
    )
    same_config = (
        "config" in manifests[0] and "config" in manifests[1]
        and manifests[0]["config"] == manifests[1]["config"]
        and manifests[0].get("config_hash") == manifests[1].get("config_hash")
    )
    artifacts = {}
    for kind in ARTIFACTS:
        entries = [manifest.get("artifacts", {}).get(kind) for manifest in manifests]
        if any(entry is None for entry in entries):
            artifacts[kind] = {"exact": False, "error": "missing_artifact_metadata"}
            continue
        paths = [manifest_path.parent / entry["file"] for manifest_path, entry in zip((left, right), entries)]
        if not all(path.is_file() for path in paths):
            artifacts[kind] = {"exact": False, "error": "missing_artifact_file"}
            continue
        hashes = [file_sha256(path) for path in paths]
        intact = all(actual == entry["sha256"] for actual, entry in zip(hashes, entries))
        detail = {"exact": hashes[0] == hashes[1] and intact, "integrity_ok": intact,
                  "left_sha256": hashes[0], "right_sha256": hashes[1]}
        if hashes[0] != hashes[1] and kind in ("events", "series"):
            detail["first_difference"] = first_csv_difference(*paths)
        elif hashes[0] != hashes[1] and kind in ("summary", "config"):
            objects = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
            detail["different_fields"] = [
                key for key in sorted(objects[0].keys() | objects[1].keys())
                if key not in objects[0] or key not in objects[1] or objects[0][key] != objects[1][key]
            ]
        artifacts[kind] = detail
    clean = all(manifest.get("provenance", {}).get("git_dirty") is False for manifest in manifests)
    start_captured = all(manifest.get("provenance_capture") == "runner_start" for manifest in manifests)
    passed = same_identity and same_config and clean and start_captured and all(item["exact"] for item in artifacts.values())
    return {"passed": passed, "same_identity": same_identity, "same_config": same_config,
            "clean_sources": clean, "captured_at_runner_start": start_captured, "artifacts": artifacts}
