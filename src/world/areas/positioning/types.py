"""Typed results for the positioning package."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.areas.positioning.models import Position, PositionFeature
    from world.mechanics.constants import DifficultyIndicator
    from world.mechanics.models import ChallengeApproach
    from world.mechanics.types import CapabilitySource


@dataclass(frozen=True)
class StuntOption:
    """One stunt a character could make from a feature in her place (#4675).

    ``approach`` is the strongest approach on the feature's challenge she has a capability
    for, ``capability_value`` that capability's value, and ``difficulty`` the grade the roll
    previews at.
    """

    feature: PositionFeature
    destination: Position
    approach: ChallengeApproach
    capability_value: int
    difficulty: DifficultyIndicator
    capability_source: CapabilitySource
