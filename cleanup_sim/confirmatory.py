from __future__ import annotations

from dataclasses import dataclass, replace

from .config import PlannerMode, RunConfig, ScenarioName, scenario_config


@dataclass(frozen=True)
class ExperimentArm:
    label: str
    planner_mode: PlannerMode
    hybrid_explore_entropy_threshold: float | None = None


def build_confirmatory_arms() -> list[ExperimentArm]:
    return [
        ExperimentArm(label="lawnmower", planner_mode="lawnmower"),
        ExperimentArm(label="active", planner_mode="active"),
        ExperimentArm(label="detected_tsp", planner_mode="detected_tsp"),
        ExperimentArm(label="hybrid_base", planner_mode="hybrid", hybrid_explore_entropy_threshold=0.18),
        ExperimentArm(label="hybrid_candidate_v2", planner_mode="hybrid", hybrid_explore_entropy_threshold=0.24),
    ]


def config_for_arm(scenario: ScenarioName, seed: int, arm: ExperimentArm) -> RunConfig:
    cfg = scenario_config(scenario, seed, arm.planner_mode)
    if arm.hybrid_explore_entropy_threshold is not None:
        cfg = replace(
            cfg,
            planner=replace(
                cfg.planner,
                hybrid_explore_entropy_threshold=arm.hybrid_explore_entropy_threshold,
            ),
        )
    return cfg
