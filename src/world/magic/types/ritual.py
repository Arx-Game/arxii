from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from world.conditions.models import ConditionStage
    from world.magic.models.anima import AnimaRitualPerformance
    from world.traits.models import CheckOutcome


class AnimaRitualCategory(models.TextChoices):
    """Categories of anima recovery rituals."""

    SOLITARY = "solitary", "Solitary"
    COLLABORATIVE = "collaborative", "Collaborative"
    ENVIRONMENTAL = "environmental", "Environmental"
    CEREMONIAL = "ceremonial", "Ceremonial"


@dataclass(frozen=True)
class RitualOutcome:
    """Result of a single perform_anima_ritual invocation."""

    performance: AnimaRitualPerformance
    outcome: CheckOutcome
    severity_reduced: int
    anima_recovered: int
    soulfray_stage_after: ConditionStage | None
    soulfray_resolved: bool


@dataclass(frozen=True)
class AnimaRegenTickSummary:
    """Result of a single anima_regen_tick() scheduler invocation."""

    examined: int
    regenerated: int
    engagement_blocked: int
    condition_blocked: int
