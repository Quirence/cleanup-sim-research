"""Derive regime metrics from saved runs without modifying their artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .config import GridConfig, HydroConfig, PlannerConfig, PlatformConfig, RunConfig, SensorConfig, SensorSuiteConfig, WorldConfig
from .provenance import capture_provenance, file_sha256
from .regimes import add_oracle_gaps, oracle_pair_key, run_metrics


def config_from_dict(data: dict) -> RunConfig:
    return RunConfig(**{
        **data,
        "world": WorldConfig(**data["world"]), "grid": GridConfig(**data["grid"]),
        "hydro": HydroConfig(**data["hydro"]), "platform": PlatformConfig(**data["platform"]),
        "planner": PlannerConfig(**data["planner"]),
        "sensors": SensorSuiteConfig(**{key: SensorConfig(**value) for key, value in data["sensors"].items()}),
    })


def analyze_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    # Verified modern artifacts only. Legacy summary-only series cannot supply
    # the missing configuration or an unrecorded trajectory/state snapshot.
    for kind in ("summary", "config", "events"):
        entry = manifest.get("artifacts", {}).get(kind)
        if not entry or file_sha256(path.parent / entry["file"]) != entry["sha256"]:
            raise ValueError(f"Missing or corrupted {kind} artifact: {path}")
    config = json.loads((path.parent / manifest["artifacts"]["config"]["file"]).read_text(encoding="utf-8"))
    summary = json.loads((path.parent / manifest["artifacts"]["summary"]["file"]).read_text(encoding="utf-8"))
    if config != manifest["config"] or summary != manifest["summary"]:
        raise ValueError(f"Manifest and saved config/summary differ: {path}")
    events = pd.read_csv(path.parent / manifest["artifacts"]["events"]["file"], float_precision="round_trip")
    return {
        **summary,
        **run_metrics(config_from_dict(config), summary, events),
        "oracle_pair_key": oracle_pair_key(config, manifest.get("provenance", {})),
        "source_manifest": str(path.resolve()), "source_manifest_sha256": file_sha256(path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dirs", nargs="+", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    paths = sorted({path.resolve() for directory in args.run_dirs for path in directory.glob("*_manifest.json")})
    if not paths:
        raise ValueError("No saved per-run manifests found; pass directories containing the run files.")
    rows = add_oracle_gaps([analyze_manifest(path) for path in paths])
    args.out_dir.mkdir(parents=True, exist_ok=False)
    pd.DataFrame(rows).to_csv(args.out_dir / "regime_summary.csv", index=False)
    (args.out_dir / "analysis_manifest.json").write_text(json.dumps({
        "analysis": "regime_metrics_v1", "provenance": capture_provenance(),
        "inputs": {str(path): file_sha256(path) for path in paths},
        "output_sha256": file_sha256(args.out_dir / "regime_summary.csv"),
        "aggregation": "unweighted goal_started snapshots, including queued route continuations; not selector frequency",
        "missing_values": "NaN means unavailable/undefined, never imputed as zero",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"analyzed={len(rows)}; output={args.out_dir / 'regime_summary.csv'}")


if __name__ == "__main__":
    main()
