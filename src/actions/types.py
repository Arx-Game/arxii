"""Core types for the action system."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TargetType(StrEnum):
    """What kind of target an action operates on."""

    SELF = "self"
    SINGLE = "single"
    AREA = "area"
    FILTERED_GROUP = "filtered_group"


@dataclass
class ActionResult:
    """Structured result from action execution."""

    success: bool
    message: str | None = None
    broadcast: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionAvailability:
    """Result of checking whether an action is available."""

    action_key: str
    available: bool
    reasons: list[str] = field(default_factory=list)


class ActionInterrupted(Exception):
    """Raised when a trigger stops an action's intent event."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)
