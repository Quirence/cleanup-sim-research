from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal


DistributionMode = Literal["clustered", "uniform"]
PlannerMode = Literal[
    "lawnmower",
    "lawnmower_sparse",
    "lawnmower_dense",
    "greedy",
    "active",
    "detected_tsp",
    "graph_mst",
    "hybrid",
    "hybrid_mst",
    "active_entropy",
    "active_probability",
    "active_no_distance",
]
ScenarioName = Literal["clustered_base", "clustered_noisy", "uniform_base"]


@dataclass(frozen=True)
class WorldConfig:
    width: float = 200.0
    height: float = 200.0
    depot_x: float = 10.0
    depot_y: float = 100.0
    n_debris: int = 150
    n_clusters: int = 7
    cluster_sigma_min: float = 15.0
    cluster_sigma_max: float = 30.0
    distribution: DistributionMode = "clustered"

    @property
    def depot(self) -> tuple[float, float]:
        return (self.depot_x, self.depot_y)


@dataclass(frozen=True)
class GridConfig:
    nx: int = 100
    ny: int = 100
    prior: float = 0.15


@dataclass(frozen=True)
class SensorConfig:
    name: str
    range_m: float
    fov_deg: float
    p_false: float
    det_center: float
    det_kappa: float
    bearing_sigma_deg: float
    localization_sigma_m: float


@dataclass(frozen=True)
class FusionConfig:
    camera: SensorConfig = SensorConfig(
        name="camera",
        range_m=28.0,
        fov_deg=70.0,
        p_false=0.006,
        det_center=18.0,
        det_kappa=3.0,
        bearing_sigma_deg=28.0,
        localization_sigma_m=1.4,
    )
    radar: SensorConfig = SensorConfig(
        name="radar",
        range_m=45.0,
        fov_deg=130.0,
        p_false=0.018,
        det_center=31.0,
        det_kappa=5.5,
        bearing_sigma_deg=50.0,
        localization_sigma_m=3.8,
    )


@dataclass(frozen=True)
class RobotConfig:
    speed_mps: float = 2.0
    dt_s: float = 1.0
    tmax_s: float = 7200.0
    collect_radius_m: float = 5.0
    bin_capacity_kg: float = 30.0
    return_ratio: float = 0.9
    arrival_tolerance_m: float = 1.0
    sensor_period_s: float = 10.0


@dataclass(frozen=True)
class PlannerConfig:
    mode: PlannerMode = "active"
    coverage_spacing_m: float = 22.0
    coverage_margin_m: float = 10.0
    candidate_spacing_m: float = 30.0
    replan_interval_s: float = 120.0
    active_alpha: float = 0.85
    active_mu: float = 0.55
    active_lambda: float = 0.035
    active_local_collect_weight: float = 45.0
    active_reference_cell_area_m2: float = 4.0
    active_b_low: float = 0.35
    active_b_high: float = 0.92
    detected_confirm_prob: float = 0.72
    detected_nms_radius_m: float = 6.0
    detected_batch_size: int = 10
    hybrid_min_confirmed_targets: int = 3
    hybrid_explore_entropy_threshold: float = 0.18
    hybrid_target_batch_size: int = 8
    target_confirm_hits: int = 2
    target_min_sensor_types: int = 2
    target_stale_after_s: float = 1800.0
    target_false_suppress_radius_m: float = 12.0
    max_path_m: float = 14400.0


@dataclass(frozen=True)
class RunConfig:
    seed: int = 11
    scenario: ScenarioName = "clustered_base"
    world: WorldConfig = WorldConfig()
    grid: GridConfig = GridConfig()
    fusion: FusionConfig = FusionConfig()
    robot: RobotConfig = RobotConfig()
    planner: PlannerConfig = PlannerConfig()

    def to_dict(self) -> dict:
        return asdict(self)


def scenario_config(name: ScenarioName, seed: int, mode: PlannerMode) -> RunConfig:
    world = WorldConfig()
    fusion = FusionConfig()
    if name == "clustered_noisy":
        fusion = FusionConfig(
            camera=SensorConfig(
                name="camera",
                range_m=24.0,
                fov_deg=65.0,
                p_false=0.018,
                det_center=14.0,
                det_kappa=4.5,
                bearing_sigma_deg=34.0,
                localization_sigma_m=2.4,
            ),
            radar=SensorConfig(
                name="radar",
                range_m=40.0,
                fov_deg=125.0,
                p_false=0.045,
                det_center=24.0,
                det_kappa=8.0,
                bearing_sigma_deg=58.0,
                localization_sigma_m=5.5,
            ),
        )
    elif name == "uniform_base":
        world = WorldConfig(distribution="uniform")

    planner = PlannerConfig(mode=mode)
    if mode == "lawnmower_dense":
        planner = replace(planner, coverage_spacing_m=10.0)
    elif mode == "lawnmower_sparse":
        planner = replace(planner, coverage_spacing_m=22.0)
    return RunConfig(seed=seed, scenario=name, world=world, fusion=fusion, planner=planner)


def ensure_output_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
