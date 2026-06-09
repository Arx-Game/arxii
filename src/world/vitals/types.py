"""Types for vitals service layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.checks.types import ModifierBreakdown
    from world.conditions.models import ConditionTemplate


@dataclass
class DamageConsequenceResult:
    """Result of processing damage consequences for a character.

    Returned by process_damage_consequences() to describe what happened
    after damage was applied.
    """

    knocked_out: bool = False
    dying: bool = False
    wounds_applied: list[ConditionTemplate] = field(default_factory=list)
    message: str = ""
    modifier_breakdown: ModifierBreakdown | None = None
