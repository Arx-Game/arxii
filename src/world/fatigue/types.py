"""Type definitions for the fatigue system."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
    check_result: Any | None


@dataclass
class RestResult:
    """Result of a rest attempt."""

    success: bool
    message: str
