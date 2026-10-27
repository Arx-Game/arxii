"""Drift types: carried drift and the focus check (#4732); drift correction (#4733)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from decimal import Decimal

    from world.items.models import ItemInstance
    from world.magic.constants import ComponentMode
    from world.magic.models import Affinity
    from world.magic.models.affinity import Resonance


@dataclass(frozen=True)
class DriftReading:
    """How much off-aura drift a character carries against her acting aura.

    ``drift`` is the weighted sum of her balances in affinities other than the
    dominant one; ``threshold`` is the point it must pass; ``steps_past`` is how
    many ``severity_step`` bands it has passed by (0 at or below the threshold).
    ``dominant_affinity`` is None, and every number 0, when she has no aura to
    measure against.
    """

    drift: int
    threshold: int
    steps_past: int
    dominant_affinity: Affinity | None


@dataclass(frozen=True)
class FocusOutcome:
    """The result of one focus check against carried drift.

    ``steps`` is the severity the check was rolled at; ``applied_severity`` is the
    severity added to the conflict condition (0 when she kept her focus).
    """

    success_level: int
    steps: int
    applied_severity: int


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


@dataclass(frozen=True)
class DriftOfferCapOption:
    """One cap of an offer, as a player sees it: what may be converted and what to offer up.

    ``qualifying`` is the carried items that count toward the rite's offering for this
    target, each with the route it took.
    """

    target_resonance: Resonance
    preview: DriftConversionPreview
    qualifying: tuple[QualifyingComponent, ...]
