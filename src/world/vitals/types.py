"""Types for vitals service layer."""

from __future__ import annotations

from dataclasses import dataclass, field

from world.vitals.constants import CharacterStatus


@dataclass
class DamageConsequenceResult:
    """Result of processing damage consequences for a character.

    Returned by process_damage_consequences() to describe what happened
    after damage was applied.
    """

    final_status: str = CharacterStatus.ALIVE
    knocked_out: bool = False
    dying: bool = False
    wounds_applied: list = field(default_factory=list)
    dying_final_round: bool = False
    message: str = ""
