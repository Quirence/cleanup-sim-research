from __future__ import annotations

import math
from dataclasses import asdict, dataclass, replace
from typing import Literal


DistributionMode = Literal["clustered", "uniform"]
ScenarioName = Literal["static_calm", "weak_drift", "strong_drift", "robot_disturbed"]
PlannerMode = Literal[
    "coverage",
    "lawnmower_survey",
    "lawnmower_collect",
    "greedy",
    "active",
    "confirmed_route",
    "oracle_perfect_static",
    "oracle_current_physics",
    "oracle_route_heuristic",
]
ParameterProfile = Literal["low", "nominal", "high"]


@dataclass(frozen=True)
class WorldConfig:
    width_m: float = 200.0
    height_m: float = 200.0
    depot_x_m: float = 10.0
    depot_y_m: float = 100.0
    n_debris: int = 150
    n_clusters: int = 7
    cluster_sigma_min_m: float = 10.0
    cluster_sigma_max_m: float = 24.0
    distribution: DistributionMode = "clustered"

    @property
    def depot(self) -> tuple[float, float]:
        return (self.depot_x_m, self.depot_y_m)


@dataclass(frozen=True)
class GridConfig:
    nx: int = 100
    ny: int = 100
    prior_expected_count_per_cell: float | None = None
    prediction_decay_per_step: float = 0.001


@dataclass(frozen=True)
class PlatformConfig:
    cruise_speed_mps: float = 1.0
    collection_speed_mps: float = 0.6
    dt_s: float = 1.0
    physics_substeps: int = 4
    tmax_s: float = 5400.0
    max_path_m: float = 3600.0
    arrival_tolerance_m: float = 1.0
    turn_rate_rad_s: float = 0.7
    sensor_period_s: float = 2.0
    collection_width_m: float = 1.0
    collection_length_m: float = 1.8
    collection_approach_radius_m: float = 6.0
    target_dwell_time_s: float = 4.0
    capture_probability: float = 0.75
    capture_time_s: float = 2.0
    collection_throughput_kg_s: float = 0.8
    bin_capacity_kg: float = 30.0
    return_ratio: float = 0.9


@dataclass(frozen=True)
class HydroConfig:
    current_x_mps: float = 0.0
    current_y_mps: float = 0.0
    wind_x_mps: float = 0.0
    wind_y_mps: float = 0.0
    windage: float = 0.0
    diffusivity_m2_s: float = 0.0
    robot_repulsion_enabled: bool = False
    robot_repulsion_radius_m: float = 4.0
    robot_repulsion_gain_mps: float = 0.35


@dataclass(frozen=True)
class SensorConfig:
    name: str
    range_m: float
    fov_deg: float
    p_detect_max: float
    decay_range_m: float
    min_detectable_size_m: float
    localization_sigma_m: float
    localization_sigma_per_m: float
    clutter_rate_per_m2: float
    confidence_sigma: float


@dataclass(frozen=True)
class SensorSuiteConfig:
    camera: SensorConfig = SensorConfig(
        name="camera",
        range_m=25.0,
        fov_deg=70.0,
        p_detect_max=0.82,
        decay_range_m=18.0,
        min_detectable_size_m=0.08,
        localization_sigma_m=0.8,
        localization_sigma_per_m=0.025,
        clutter_rate_per_m2=2.5e-5,
        confidence_sigma=0.08,
    )
    radar: SensorConfig = SensorConfig(
        name="radar",
        range_m=45.0,
        fov_deg=120.0,
        p_detect_max=0.62,
        decay_range_m=34.0,
        min_detectable_size_m=0.16,
        localization_sigma_m=1.8,
        localization_sigma_per_m=0.055,
        clutter_rate_per_m2=7.5e-5,
        confidence_sigma=0.12,
    )

    @property
    def sensors(self) -> tuple[SensorConfig, SensorConfig]:
        return (self.camera, self.radar)


@dataclass(frozen=True)
class PlannerConfig:
    mode: PlannerMode = "active"
    coverage_spacing_m: float = 14.0
    coverage_margin_m: float = 6.0
    candidate_spacing_m: float = 20.0
    replan_interval_s: float = 45.0
    active_entropy_weight: float = 1.0
    active_density_weight: float = 1.8
    active_distance_weight: float = 0.018
    greedy_tabu_radius_m: float = 3.0
    target_confirm_confidence: float = 0.62
    target_confirm_hits: int = 2
    target_min_sensor_types: int = 1
    target_nms_radius_m: float = 4.0
    target_stale_after_s: float = 300.0
    target_suppression_radius_m: float = 6.0
    route_batch_size: int = 10


@dataclass(frozen=True)
class RunConfig:
    seed: int = 0
    scenario: ScenarioName = "weak_drift"
    profile: ParameterProfile = "nominal"
    world: WorldConfig = WorldConfig()
    grid: GridConfig = GridConfig()
    platform: PlatformConfig = PlatformConfig()
    hydro: HydroConfig = HydroConfig()
    sensors: SensorSuiteConfig = SensorSuiteConfig()
    planner: PlannerConfig = PlannerConfig()

    def to_dict(self) -> dict:
        return asdict(self)


def _profile_platform(profile: ParameterProfile, base: PlatformConfig) -> PlatformConfig:
    if profile == "low":
        return replace(
            base,
            collection_speed_mps=0.45,
            cruise_speed_mps=0.8,
            collection_width_m=0.6,
            capture_probability=0.62,
            bin_capacity_kg=15.0,
        )
    if profile == "high":
        return replace(
            base,
            collection_speed_mps=0.8,
            cruise_speed_mps=1.3,
            collection_width_m=1.5,
            capture_probability=0.86,
            bin_capacity_kg=60.0,
        )
    return base


def _profile_sensors(profile: ParameterProfile, base: SensorSuiteConfig) -> SensorSuiteConfig:
    if profile == "low":
        return SensorSuiteConfig(
            camera=replace(
                base.camera,
                range_m=20.0,
                p_detect_max=0.68,
                localization_sigma_m=1.2,
                clutter_rate_per_m2=5.0e-5,
            ),
            radar=replace(
                base.radar,
                range_m=36.0,
                p_detect_max=0.50,
                localization_sigma_m=2.5,
                clutter_rate_per_m2=1.3e-4,
            ),
        )
    if profile == "high":
        return SensorSuiteConfig(
            camera=replace(
                base.camera,
                range_m=30.0,
                p_detect_max=0.90,
                localization_sigma_m=0.55,
                clutter_rate_per_m2=1.2e-5,
            ),
            radar=replace(
                base.radar,
                range_m=55.0,
                p_detect_max=0.72,
                localization_sigma_m=1.3,
                clutter_rate_per_m2=4.0e-5,
            ),
        )
    return base


def survey_lawnmower_spacing_m(sensors: SensorSuiteConfig) -> float:
    camera = sensors.camera
    effective_swath = 2.0 * camera.decay_range_m * math.sin(math.radians(camera.fov_deg) * 0.5)
    return max(4.0, 0.70 * effective_swath)


def scenario_config(
    name: ScenarioName,
    seed: int,
    mode: PlannerMode,
    profile: ParameterProfile = "nominal",
) -> RunConfig:
    world = WorldConfig()
    hydro = HydroConfig()
    if name == "static_calm":
        hydro = HydroConfig()
    elif name == "weak_drift":
        hydro = HydroConfig(
            current_x_mps=0.018,
            current_y_mps=-0.006,
            wind_x_mps=2.0,
            wind_y_mps=0.5,
            windage=0.008,
            diffusivity_m2_s=0.015,
        )
    elif name == "strong_drift":
        hydro = HydroConfig(
            current_x_mps=0.055,
            current_y_mps=-0.018,
            wind_x_mps=4.0,
            wind_y_mps=1.0,
            windage=0.015,
            diffusivity_m2_s=0.05,
        )
    elif name == "robot_disturbed":
        hydro = HydroConfig(
            current_x_mps=0.02,
            current_y_mps=0.0,
            wind_x_mps=2.5,
            wind_y_mps=-0.5,
            windage=0.01,
            diffusivity_m2_s=0.02,
            robot_repulsion_enabled=True,
        )

    platform = _profile_platform(profile, PlatformConfig())
    sensors = _profile_sensors(profile, SensorSuiteConfig())
    planner = PlannerConfig(mode=mode)
    if mode in {"coverage", "lawnmower_survey"}:
        planner = replace(planner, coverage_spacing_m=survey_lawnmower_spacing_m(sensors))
    elif mode == "lawnmower_collect":
        planner = replace(planner, coverage_spacing_m=max(0.25, 0.8 * platform.collection_width_m))
    return RunConfig(
        seed=seed,
        scenario=name,
        profile=profile,
        world=world,
        platform=platform,
        hydro=hydro,
        sensors=sensors,
        planner=planner,
    )
