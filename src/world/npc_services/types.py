"""Value types for NPC services (#4091)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AllegianceEnding:
    """How an allegiance hold ended: which condition, and the authored result picked."""

    condition_name: str
    consequence_label: str | None


@dataclass(frozen=True)
class AllegianceBreakResult:
    """A striker's break roll against an allegiance hold (Decision 16)."""

    condition_name: str
    difficulty: int
    strength: int
    resistance: int
    pressure: int
    broke: bool
    ending: AllegianceEnding | None
