"""Drift correction types (#4733, slice 4 of #4672)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from decimal import Decimal

    from world.items.models import ItemInstance
    from world.magic.constants import ComponentMode


@dataclass(frozen=True)
class QualifyingComponent:
    """An item that counts toward a target-resonance ritual component, and the route it took."""

    item: ItemInstance
    mode: ComponentMode


@dataclass(frozen=True)
class DriftSourceOption:
    """One drift holding the rite could convert toward a target, and what it would yield.

    ``max_amount`` is the most of it the offer's cap and the balance allow;
    ``projected_output`` is what converting all of that yields at a full share.
    """

    resonance_id: int
    resonance_name: str
    balance: int
    multiplier: Decimal
    conversion_type: str
    max_amount: int
    projected_output: int


@dataclass(frozen=True)
class DriftConversionPreview:
    """What a character may convert toward ``target_resonance_id`` under an offer."""

    target_resonance_id: int
    cap_remaining: int
    sources: tuple[DriftSourceOption, ...]
    focus_bonus: int


@dataclass(frozen=True)
class DriftCorrectionResult:
    """The outcome of one performance of the drift correction rite.

    ``converted_amount`` is the source units moved (0 on a tier with no share);
    ``granted_amount`` is what the target gained.
    """

    source_resonance_id: int
    target_resonance_id: int
    attempted_amount: int
    converted_amount: int
    granted_amount: int
    outcome_name: str
    success_level: int
    conversion_type: str
    focus_bonus: int
