from __future__ import annotations

from enum import Enum

from .config import PlannerConfig


class HybridDecision(str, Enum):
    EXPLORE = "explore"
    ROUTE = "route"


def choose_hybrid_mode(
    mean_entropy: float,
    confirmed_target_count: int,
    planner: PlannerConfig,
) -> HybridDecision:
    if (
        confirmed_target_count >= planner.hybrid_min_confirmed_targets
        and mean_entropy <= planner.hybrid_explore_entropy_threshold
    ):
        return HybridDecision.ROUTE
    return HybridDecision.EXPLORE
