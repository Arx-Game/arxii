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
    ``catastrophe`` marks the nothing-lands case.  ``cancelled`` marks
    a pre-collect reactive cancellation (#2218): a trigger cancelled the
    collection before the check was rolled — the pool was *not* zeroed.
    """

    gathered: int
    landed: int
    overflow: int
    success_level: int
    catastrophe: bool = False
    cancelled: bool = False


@dataclass(frozen=True)
class FoodTransferResult:
    """Outcome of one inter-domain food transfer.

    ``amount`` is what was requested; ``landed`` is what reached the
    target stockpile after the capacity cap; ``overflow`` is what was
    lost (target granary full). ``cancelled`` marks a pre-transfer
    reactive cancellation — no food was moved.
    """

    amount: int
    landed: int
    overflow: int
    cancelled: bool = False
