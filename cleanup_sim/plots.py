from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .config import ensure_output_dir
from .simulation import SimulationResult


def plot_single_result(result: SimulationResult, out_dir: Path, prefix: str) -> list[Path]:
    ensure_output_dir(out_dir)
    paths: list[Path] = []
    world = result.config.world

    fig, ax = plt.subplots(figsize=(7, 6))
    ax.scatter(result.field.positions[:, 0], result.field.positions[:, 1], s=10, c="#6b7280", label="Весь мусор")
    if np.any(result.field.collected):
        ax.scatter(
            result.field.positions[result.field.collected, 0],
            result.field.positions[result.field.collected, 1],
            s=18,
            marker="x",
            c="#dc2626",
            label="Собранное",
        )
    ax.plot(result.path[:, 0], result.path[:, 1], lw=1.0, c="#2563eb", label="Траектория")
    ax.scatter([world.depot_x], [world.depot_y], marker="s", s=70, c="#16a34a", label="База")
    ax.set_xlim(0, world.width)
    ax.set_ylim(0, world.height)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("x, м")
    ax.set_ylabel("y, м")
    ax.set_title(f"Траектория: {result.config.scenario}, {result.config.planner.mode}, seed={result.config.seed}")
    ax.grid(alpha=0.25)
    ax.legend(fontsize="small")
    p = out_dir / f"{prefix}_trajectory.png"
    fig.tight_layout()
    fig.savefig(p, dpi=180)
    plt.close(fig)
    paths.append(p)

    fig, ax = plt.subplots(figsize=(7, 5.8))
    im = ax.imshow(result.belief, origin="lower", extent=[0, world.width, 0, world.height], aspect="auto")
    ax.scatter([world.depot_x], [world.depot_y], marker="s", s=50, c="#16a34a")
    ax.set_xlabel("x, м")
    ax.set_ylabel("y, м")
    ax.set_title("Апостериорная карта вероятности мусора")
    fig.colorbar(im, ax=ax, label="P(мусор)")
    p = out_dir / f"{prefix}_belief.png"
    fig.tight_layout()
    fig.savefig(p, dpi=180)
    plt.close(fig)
    paths.append(p)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(result.series["path_m"], result.series["collected_ratio"], c="#111827", lw=1.6)
    ax.set_xlabel("Пройденный путь, м")
    ax.set_ylabel("Доля собранного мусора")
    ax.set_ylim(0, 1.02)
    ax.set_title("Динамика сбора по длине пути")
    ax.grid(alpha=0.3)
    p = out_dir / f"{prefix}_collected_vs_path.png"
    fig.tight_layout()
    fig.savefig(p, dpi=180)
    plt.close(fig)
    paths.append(p)
    return paths


def plot_experiment_curves(summary_dir: Path, out_dir: Path) -> list[Path]:
    ensure_output_dir(out_dir)
    series_files = list(summary_dir.glob("*_series.csv"))
    if not series_files:
        return []
    rows = []
    for path in series_files:
        parts = path.stem.replace("_series", "").split("__")
        if len(parts) != 3:
            continue
        scenario, mode, seed = parts
        df = pd.read_csv(path)
        if df.empty:
            continue
        df["scenario"] = scenario
        df["mode"] = mode
        df["seed"] = int(seed.replace("seed", ""))
        rows.append(df)
    if not rows:
        return []
    data = pd.concat(rows, ignore_index=True)
    paths: list[Path] = []
    for scenario, sdf in data.groupby("scenario"):
        paths.append(_plot_mean_curve(sdf, out_dir, scenario, "path_m", "Пройденный путь, м", "path"))
        paths.append(_plot_mean_curve(sdf, out_dir, scenario, "time_s", "Время, с", "time"))
    aggregate_path = summary_dir.parent / "aggregate_mean_std.csv"
    if aggregate_path.exists():
        aggregate = pd.read_csv(aggregate_path)
        if not aggregate.empty:
            paths.extend(_plot_aggregate_bars(aggregate, out_dir))
    return paths


def _plot_mean_curve(data: pd.DataFrame, out_dir: Path, scenario: str, x_col: str, x_label: str, suffix: str) -> Path:
    fig, ax = plt.subplots(figsize=(8, 5))
    for mode, mdf in data.groupby("mode"):
        max_x = float(mdf[x_col].max())
        grid = np.linspace(0, max_x, 120)
        curves = []
        for _, run in mdf.groupby("seed"):
            curves.append(
                np.interp(
                    grid,
                    run[x_col],
                    run["collected_ratio"],
                    left=0,
                    right=run["collected_ratio"].iloc[-1],
                )
            )
        curve_arr = np.vstack(curves)
        mean = curve_arr.mean(axis=0)
        std = curve_arr.std(axis=0)
        ax.plot(grid, mean, lw=1.6, label=mode)
        ax.fill_between(grid, np.clip(mean - std, 0.0, 1.0), np.clip(mean + std, 0.0, 1.0), alpha=0.12)
    title_suffix = "пути" if suffix == "path" else "времени"
    ax.set_title(f"Средняя доля сбора по {title_suffix}: {scenario}")
    ax.set_xlabel(x_label)
    ax.set_ylabel("Доля собранного мусора")
    ax.set_ylim(0, 1.02)
    ax.grid(alpha=0.3)
    ax.legend(fontsize="small")
    p = out_dir / f"{scenario}_mean_collected_vs_{suffix}.png"
    fig.tight_layout()
    fig.savefig(p, dpi=180)
    plt.close(fig)
    return p


def _plot_aggregate_bars(aggregate: pd.DataFrame, out_dir: Path) -> list[Path]:
    paths: list[Path] = []
    specs = [
        ("brier_score_mean", "brier_score_std", "Brier score", "map_quality_by_mode"),
        ("false_visits_mean", "false_visits_std", "Ложные посещения", "false_visits_by_mode"),
    ]
    for scenario, sdf in aggregate.groupby("scenario"):
        for mean_col, std_col, ylabel, suffix in specs:
            if mean_col not in sdf:
                continue
            fig, ax = plt.subplots(figsize=(8, 4.8))
            x = np.arange(len(sdf))
            yerr = sdf[std_col].to_numpy() if std_col in sdf else None
            ax.bar(x, sdf[mean_col].to_numpy(), yerr=yerr, capsize=3, color="#4b5563")
            ax.set_xticks(x)
            ax.set_xticklabels(sdf["mode"], rotation=30, ha="right")
            ax.set_ylabel(ylabel)
            ax.set_title(f"{ylabel}: {scenario}")
            ax.grid(axis="y", alpha=0.25)
            p = out_dir / f"{scenario}_{suffix}.png"
            fig.tight_layout()
            fig.savefig(p, dpi=180)
            plt.close(fig)
            paths.append(p)
    return paths
