"""Typed result shapes for agriculture services."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FoodCollectionResult:
    """Outcome of one food collection dispatch from a Field.

    ``gathered`` is what the collector set out with (the pool, zeroed by
    the attempt); ``landed`` is what reached the stockpile after the
    outcome band; ``overflow`` is what was lost above the Granary's
    capacity; ``success_level`` is the check band that decided it.
    ``catastrophe`` marks the nothing-lands case.
    """

    gathered: int
    landed: int
    overflow: int
    success_level: int
    catastrophe: bool = False
