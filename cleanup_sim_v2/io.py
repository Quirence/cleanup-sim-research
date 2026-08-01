from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .simulation import RunResult


def save_run(result: RunResult, out_dir: Path, prefix: str) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary": out_dir / f"{prefix}_summary.json",
        "series": out_dir / f"{prefix}_series.csv",
        "events": out_dir / f"{prefix}_events.csv",
        "density": out_dir / f"{prefix}_density.npy",
        "positions": out_dir / f"{prefix}_positions.npy",
        "config": out_dir / f"{prefix}_config.json",
    }
    paths["summary"].write_text(json.dumps(result.summary, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["config"].write_text(json.dumps(result.config.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    result.series.to_csv(paths["series"], index=False)
    result.events.to_csv(paths["events"], index=False)
    np.save(paths["density"], result.density_map.expected_count)
    np.save(paths["positions"], result.field.positions)
    return paths
