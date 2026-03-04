"""Type definitions for the obstacles system."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.checks.models import CheckType
    from world.checks.types import CheckResult
    from world.obstacles.models import BypassOption, ObstacleInstance


@dataclass
class BypassAvailability:
    """A bypass option's availability for a specific character."""

    bypass_option: BypassOption
    can_attempt: bool
    missing_capabilities: list[str] = field(default_factory=list)
    check_type: CheckType | None = None
    effective_difficulty: int = 0


@dataclass
class ObstacleDetail:
    """An obstacle instance with its available bypass options for a character."""

    obstacle_instance: ObstacleInstance
    description: str
    bypass_options: list[BypassAvailability] = field(default_factory=list)


@dataclass
class BypassAttemptResult:
    """Result of attempting to bypass an obstacle."""

    success: bool
    message: str = ""
    check_result: CheckResult | None = None
    obstacle_destroyed: bool = False
    obstacle_suppressed_rounds: int = 0
