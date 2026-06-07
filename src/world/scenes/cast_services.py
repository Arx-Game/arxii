"""Service functions for standalone technique casts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.scenes.action_constants import CAST_DIFFICULTY_BANDS

if TYPE_CHECKING:
    from world.magic.models import Technique


def derive_cast_difficulty(technique: Technique) -> int:
    """Difficulty for a standalone cast, sourced from the technique's authored intensity."""
    intensity = technique.intensity or 1
    for ceiling, difficulty in CAST_DIFFICULTY_BANDS:
        if intensity <= ceiling:
            return difficulty
    return CAST_DIFFICULTY_BANDS[-1][1]
