from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from world.conditions.models import ConditionStage, ConditionTemplate
    from world.magic.models.anima import AnimaRitualPerformance
    from world.mechanics.models import Property
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
class SoulfrayContent:
    """Composite result from _SoulfrayContentFactory.

    Holds the seeded Soulfray ConditionTemplate, all 5 ordered stages (Fraying
    through Unravelling), and the blocks_anima_regen Property so callers can
    reference any piece without additional DB lookups.

    stages list index:
      0 → Fraying    (stage_order=1, severity_threshold=1)
      1 → Tearing    (stage_order=2, severity_threshold=6,  +blocks_anima_regen)
      2 → Ripping    (stage_order=3, severity_threshold=16, +blocks_anima_regen)
      3 → Sundering  (stage_order=4, severity_threshold=36, +blocks_anima_regen)
      4 → Unravelling(stage_order=5, severity_threshold=66, +blocks_anima_regen)
    """

    template: ConditionTemplate
    stages: list[ConditionStage] = field(default_factory=list)
    blocks_anima_regen: Property | None = None


@dataclass(frozen=True)
class AnimaRegenTickSummary:
    """Result of a single anima_regen_tick() scheduler invocation."""

    examined: int
    regenerated: int
    engagement_blocked: int
    condition_blocked: int
