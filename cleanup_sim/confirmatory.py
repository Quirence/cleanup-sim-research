from __future__ import annotations

from dataclasses import dataclass, replace

from .config import PlannerMode, RunConfig, ScenarioName, scenario_config


FINAL_HYBRID_LABEL = "hybrid_final_v1"
FINAL_HYBRID_EXPLORE_ENTROPY_THRESHOLD = 0.24


@dataclass(frozen=True)
class ExperimentArm:
    label: str
    planner_mode: PlannerMode
    hybrid_explore_entropy_threshold: float | None = None


def build_confirmatory_arms() -> list[ExperimentArm]:
    return [
        ExperimentArm(label="lawnmower_sparse", planner_mode="lawnmower_sparse"),
        ExperimentArm(label="lawnmower_dense", planner_mode="lawnmower_dense"),
        ExperimentArm(label="greedy", planner_mode="greedy"),
        ExperimentArm(label="active", planner_mode="active"),
        ExperimentArm(label="detected_tsp", planner_mode="detected_tsp"),
        ExperimentArm(label="hybrid_base", planner_mode="hybrid", hybrid_explore_entropy_threshold=0.18),
        ExperimentArm(
            label=FINAL_HYBRID_LABEL,
            planner_mode="hybrid",
            hybrid_explore_entropy_threshold=FINAL_HYBRID_EXPLORE_ENTROPY_THRESHOLD,
        ),
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
