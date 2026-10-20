"""Type definitions for check-based technique training (#2727)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.magic.models import CharacterTechnique


@dataclass(frozen=True)
class TrainingCheckResult:
    """Outcome of a check-based training session (#2727).

    Returned by resolve_training_check.
    """

    outcome_name: str
    success_level: int
    dev_point_multiplier: Decimal
    dev_points_contributed: int
    ap_spent: int
    technique_acquired: CharacterTechnique | None


@dataclass(frozen=True)
class TechniqueTeachingSources:
    """Where a technique is taught right now (#4501).

    ``academy_names`` are the organizations fronting a TRAIN offer for it;
    ``player_teacher_count`` is the number of open player teaching offers.
    """

    academy_names: tuple[str, ...]
    player_teacher_count: int

    @property
    def is_taught(self) -> bool:
        return bool(self.academy_names) or self.player_teacher_count > 0
