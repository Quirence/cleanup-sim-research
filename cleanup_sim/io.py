from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .config import ensure_output_dir
from .simulation import SimulationResult


def save_result(result: SimulationResult, out_dir: Path, prefix: str) -> dict[str, Path]:
    ensure_output_dir(out_dir)
    paths = {
        "summary": out_dir / f"{prefix}_summary.json",
        "events": out_dir / f"{prefix}_events.csv",
        "series": out_dir / f"{prefix}_series.csv",
        "path": out_dir / f"{prefix}_path.npy",
        "belief": out_dir / f"{prefix}_belief.npy",
        "true_occ": out_dir / f"{prefix}_true_occ.npy",
        "residual_true_occ": out_dir / f"{prefix}_residual_true_occ.npy",
        "config": out_dir / f"{prefix}_config.json",
    }
    paths["summary"].write_text(json.dumps(result.summary, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["config"].write_text(json.dumps(result.config.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    result.events.to_csv(paths["events"], index=False)
    result.series.to_csv(paths["series"], index=False)
    np.save(paths["path"], result.path)
    np.save(paths["belief"], result.belief)
    np.save(paths["true_occ"], result.true_occ)
    np.save(paths["residual_true_occ"], result.residual_true_occ)
    return paths
