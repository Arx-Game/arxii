"""Type definitions for the fatigue system."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.checks.types import CheckResult


@dataclass
class ActionResult:
    """Result of an action executed through the fatigue pipeline."""

    fatigue_applied: int
    effort_level: str
    fatigue_zone: str
    collapse_triggered: bool
    collapsed: bool
    powered_through: bool
    strain_damage: int
    check_result: CheckResult | None
    level_ups: list[tuple[str, int, int]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.level_ups is None:
            self.level_ups = []


@dataclass
class RestResult:
    """Result of a rest attempt."""

    success: bool
    message: str
