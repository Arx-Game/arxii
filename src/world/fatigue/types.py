"""Type definitions for the fatigue system."""

from __future__ import annotations

from dataclasses import dataclass, field
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
    level_ups: list[tuple[str, int, int]] = field(default_factory=list)


@dataclass
class FatigueCollapseResult:
    """Outcome of running the fatigue collapse sequence for one category.

    The caller decides *whether* collapse risk applies (zone/effort gate); this
    captures the result of the endurance + power-through rolls and the strain
    damage applied to health.
    """

    collapsed: bool
    powered_through: bool
    strain_damage: int


@dataclass
class RestResult:
    """Result of a rest attempt."""

    success: bool
    message: str
