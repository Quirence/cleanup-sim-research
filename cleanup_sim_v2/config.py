from __future__ import annotations

import math
from dataclasses import asdict, dataclass, replace
from typing import Literal


DistributionMode = Literal["clustered", "uniform"]
ScenarioName = Literal[
    "static_calm",
    "weak_drift",
    "strong_drift",
    "robot_disturbed",
    "uniform_static_calm",
    "uniform_weak_drift",
    "uniform_strong_drift",
    "uniform_robot_disturbed",
]
PlannerMode = Literal[
    "coverage",
    "lawnmower_survey",
    "lawnmower_collect",
    "greedy",
    "active",
    "belief_horizon",
    "belief_horizon_provisional",
    "belief_cluster_route",
    "belief_orienteering",
    "belief_orienteering_provisional",
    "belief_orienteering_depth1",
    "belief_orienteering_no_opportunity_cost",
    "belief_orienteering_density_disabled",
    "belief_horizon_no_efficiency",
    "belief_horizon_no_track_prediction",
    "belief_horizon_no_refinement",
    "adaptive_mission",
    "adaptive_mission_no_route",
    "adaptive_mission_no_orienteering",
    "adaptive_mission_no_local_exploit",
    "adaptive_mission_no_hysteresis",
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
    belief_candidate_count: int = 30
    belief_density_peak_count: int = 10
    belief_entropy_peak_count: int = 8
    belief_transect_count: int = 8
    belief_expected_collection_weight: float = 2.0
    belief_information_gain_weight: float = 0.35
    belief_target_confirmation_weight: float = 0.35
    belief_path_cost_weight: float = 0.004
    belief_empty_goal_risk_weight: float = 0.25
    belief_stale_target_risk_weight: float = 0.3
    belief_efficiency_score: bool = True
    belief_efficiency_scale_m: float = 30.0
    belief_unconfirmed_candidate_max_travel_m: float = 80.0
    belief_track_prediction_enabled: bool = True
    belief_refinement_enabled: bool = True
    belief_rollout_collection_weight: float = 0.65
    belief_virtual_collection_discount: float = 0.6
    belief_transect_extension_m: float = 10.0
    belief_cluster_route_candidate_count: int = 14
    belief_cluster_route_max_points: int = 3
    belief_cluster_route_radius_m: float = 24.0
    belief_cluster_route_max_length_m: float = 90.0
    belief_cluster_route_min_points: int = 2
    belief_cluster_route_switch_margin: float = 1.0
    belief_cluster_route_confirmed_followups_only: bool = True
    # Fallback weight when a candidate's swept-path expected collection underestimates its
    # value: score = max(swept_expected_collection, belief_cluster_route_density_prior_weight
    # * local_density). Distinct from belief_orienteering_target_density_prior_weight below -
    # each algorithm's blend weight is tuned independently, not meant to be shared.
    belief_cluster_route_density_prior_weight: float = 0.35
    belief_orienteering_candidate_count: int = 16
    belief_orienteering_depth: int = 3
    belief_orienteering_min_route_points: int = 2
    belief_orienteering_beam_width: int = 6
    belief_orienteering_max_first_leg_m: float = 80.0
    belief_orienteering_max_route_m: float = 145.0
    belief_orienteering_future_discount: float = 0.72
    belief_orienteering_switch_margin: float = 0.15
    belief_orienteering_opportunity_cost_weight: float = 0.4
    belief_orienteering_density_enabled: bool = True
    belief_orienteering_entropy_enabled: bool = False
    belief_orienteering_density_prior_weight: float = 0.15
    # Same max(swept, weight * local_density) fallback blend as
    # belief_cluster_route_density_prior_weight above, but for confirmed/provisional target
    # candidates specifically (density_peak candidates use
    # belief_orienteering_density_prior_weight instead, additively).
    belief_orienteering_target_density_prior_weight: float = 0.2
    belief_orienteering_min_density_swept_count: float = 0.6
    belief_transect_collection_speed_enabled: bool = True
    belief_collection_speed_expected_count_threshold: float = 1.0
    belief_density_signal_threshold: float = 0.35
    belief_entropy_signal_threshold: float = 0.02
    belief_collect_sigma_threshold_m: float = 1.2
    belief_refine_standoff_m: float = 8.0
    belief_refine_confidence_weight: float = 0.5
    belief_require_camera_before_collection: bool = False
    belief_local_sweep_enabled: bool = False
    belief_local_sweep_lanes: int = 3
    belief_local_sweep_spacing_m: float = 0.8
    belief_provisional_targets_enabled: bool = False
    belief_provisional_min_confidence: float = 0.68
    belief_provisional_min_hits: int = 1
    belief_provisional_max_uncertainty_m: float = 3.5
    belief_provisional_confidence_scale: float = 0.65
    belief_provisional_require_camera: bool = True
    adaptive_route_enabled: bool = True
    adaptive_orienteering_enabled: bool = True
    adaptive_local_exploit_enabled: bool = True
    adaptive_hysteresis_enabled: bool = True
    adaptive_switch_margin: float = 0.12
    adaptive_route_min_confirmed: int = 6
    adaptive_route_fresh_after_s: float = 180.0
    adaptive_local_min_expected_count: float = 25.0
    adaptive_local_density_signal_threshold: float = 0.35
    adaptive_efficiency_scale_m: float = 30.0
    adaptive_expected_collection_weight: float = 2.0
    adaptive_rollout_collection_weight: float = 0.65
    adaptive_information_gain_weight: float = 0.35
    adaptive_target_confirmation_weight: float = 0.35
    adaptive_fresh_target_weight: float = 0.08
    adaptive_route_target_count_weight: float = 0.12
    adaptive_empty_goal_risk_weight: float = 0.25
    adaptive_stale_target_risk_weight: float = 0.3
    adaptive_drift_risk_weight: float = 0.6
    adaptive_route_drift_bonus_weight: float = 0.6
    adaptive_drift_reference_mps: float = 0.035
    adaptive_orienteering_max_drift_ratio: float = 2.0
    adaptive_local_exploit_max_drift_ratio: float = 2.0
    # Override fires once confirmed_route's unified-utility score reaches this
    # fraction of the best candidate's score under sustained drift with enough
    # fresh confirmed targets. With a positive best score, 1.0 cannot promote
    # a strictly worse route candidate. The selector also has separate handling
    # for nonpositive scores and applies this override after hysteresis.
    adaptive_route_drift_override_min_ratio: float = 0.6
    adaptive_route_drift_override_min_drift_ratio: float = 0.9
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


def belief_scout_spacing_m(sensors: SensorSuiteConfig) -> float:
    radar = sensors.radar
    effective_swath = 2.0 * radar.decay_range_m * math.sin(math.radians(radar.fov_deg) * 0.5)
    return max(12.0, 0.75 * effective_swath)


def scenario_config(
    name: ScenarioName,
    seed: int,
    mode: PlannerMode,
    profile: ParameterProfile = "nominal",
) -> RunConfig:
    distribution: DistributionMode = "uniform" if name.startswith("uniform_") else "clustered"
    hydro_name = name.removeprefix("uniform_")
    world = WorldConfig(distribution=distribution)
    hydro = HydroConfig()
    if hydro_name == "static_calm":
        hydro = HydroConfig()
    elif hydro_name == "weak_drift":
        hydro = HydroConfig(
            current_x_mps=0.018,
            current_y_mps=-0.006,
            wind_x_mps=2.0,
            wind_y_mps=0.5,
            windage=0.008,
            diffusivity_m2_s=0.015,
        )
    elif hydro_name == "strong_drift":
        hydro = HydroConfig(
            current_x_mps=0.055,
            current_y_mps=-0.018,
            wind_x_mps=4.0,
            wind_y_mps=1.0,
            windage=0.015,
            diffusivity_m2_s=0.05,
        )
    elif hydro_name == "robot_disturbed":
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
    if mode.startswith("belief_") or mode.startswith("adaptive_mission"):
        planner = replace(planner, coverage_spacing_m=belief_scout_spacing_m(sensors))
    if mode in {"belief_horizon_provisional", "belief_orienteering_provisional"}:
        planner = replace(planner, belief_provisional_targets_enabled=True)
    if mode == "belief_horizon_no_efficiency":
        planner = replace(planner, belief_efficiency_score=False)
    elif mode == "belief_horizon_no_track_prediction":
        planner = replace(planner, belief_track_prediction_enabled=False)
    elif mode == "belief_horizon_no_refinement":
        planner = replace(planner, belief_refinement_enabled=False)
    elif mode == "belief_orienteering_depth1":
        planner = replace(planner, belief_orienteering_depth=1, belief_orienteering_min_route_points=1)
    elif mode == "belief_orienteering_no_opportunity_cost":
        planner = replace(planner, belief_orienteering_opportunity_cost_weight=0.0)
    elif mode == "belief_orienteering_density_disabled":
        planner = replace(planner, belief_orienteering_density_enabled=False)
    elif mode == "adaptive_mission_no_route":
        planner = replace(planner, adaptive_route_enabled=False)
    elif mode == "adaptive_mission_no_orienteering":
        planner = replace(planner, adaptive_orienteering_enabled=False)
    elif mode == "adaptive_mission_no_local_exploit":
        planner = replace(planner, adaptive_local_exploit_enabled=False)
    elif mode == "adaptive_mission_no_hysteresis":
        planner = replace(planner, adaptive_hysteresis_enabled=False)
    if mode in {"coverage", "lawnmower_survey"}:
        planner = replace(planner, coverage_spacing_m=survey_lawnmower_spacing_m(sensors))
    elif mode == "lawnmower_collect":
        planner = replace(
            planner,
            coverage_spacing_m=max(0.25, 0.8 * platform.collection_width_m),
            coverage_margin_m=max(0.0, 0.5 * platform.collection_width_m),
        )
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
