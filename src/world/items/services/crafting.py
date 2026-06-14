"""Services: check-driven facet crafting (Spec D PR2 / #510)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.items.models import FacetCraftingConfig

if TYPE_CHECKING:
    from world.checks.types import CheckResult


def get_facet_crafting_config() -> FacetCraftingConfig:
    """Lazy-create and return the singleton crafting config (pk=1)."""
    config, _ = FacetCraftingConfig.objects.get_or_create(pk=1)
    return config


def compute_quality_score(check_result: CheckResult, *, step: int, min_success_level: int) -> int:
    """Quality score = total_points + (success_level - min_success_level) * step.

    Reads only ``total_points`` and ``success_level`` off the CheckResult.
    The graded outcome shifts the score above the crafter's raw skill points.
    """
    bonus = max(0, check_result.success_level - min_success_level) * step
    return check_result.total_points + bonus
