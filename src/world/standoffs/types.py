"""Result types for standoff verbs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.standoffs.models import StandoffReveal


@dataclass(frozen=True)
class StandoffActionResult:
    """What a standoff verb did. ``success`` is False when the verb was refused or failed."""

    success: bool
    message: str
    success_level: int | None = None
    revealed: list[StandoffReveal] = field(default_factory=list)
    fight_started: bool = False
    settled: bool = False
    morale_line: str = ""
