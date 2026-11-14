"""Drift types: the unsettled reading and focus check (#4732, #5123); correction (#4733)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from decimal import Decimal

    from world.items.models import ItemInstance
    from world.magic.constants import ComponentMode
    from world.magic.models import Affinity
    from world.magic.models.affinity import Resonance


@dataclass(frozen=True)
class DriftReading:
    """Whether a character is unsettled: affinities grown past who they are (#5123).

    Read on the true aura. ``own_shares`` is each affinity's percent of the character's own
    lifetime resonance (the Mire excluded); ``settled_shares`` is who they are, per
    affinity. ``main_affinity`` is the largest settled share. ``excess_percent`` is how far
    the non-main affinities stand past their settled shares plus the tolerance, with the
    Sineater's Mire share past its allowance added; ``steps_past`` is how many
    ``unsettled_step_percent`` bands that is (0 when settled). ``leading_excess_resonance``
    is the resonance contributing most to the excess. ``mire_share_percent`` is the Mire's
    share of all the character's lifetime resonance, shown apart from their own.
    ``main_affinity`` is None, and every number 0, when she has no settled aura to measure
    against. ``own_excess_points`` and ``mire_excess_points`` are the excess per affinity pk
    in lifetime points, which is what atoning may convert (the Mire part first).
    """

    steps_past: int
    main_affinity: Affinity | None
    leading_excess_resonance: Resonance | None
    excess_percent: Decimal
    mire_share_percent: Decimal
    own_shares: dict[int, Decimal]
    settled_shares: dict[int, Decimal]
    own_excess_points: dict[int, int] = field(default_factory=dict)
    mire_excess_points: dict[int, int] = field(default_factory=dict)

    def convertible_points(self, affinity_id: int) -> int:
        """Lifetime points that atoning may convert away from ``affinity_id`` (0 if none)."""
        return self.own_excess_points.get(affinity_id, 0) + self.mire_excess_points.get(
            affinity_id, 0
        )


@dataclass(frozen=True)
class AcceptAuraResult:
    """What accepting the changes to the aura did.

    ``mire_moved`` is the lifetime resonance taken from the Mire that became the
    character's own; ``settled_shares`` is who they are now, per affinity pk.
    """

    mire_moved: int
    main_affinity: Affinity | None
    settled_shares: dict[int, Decimal]


@dataclass(frozen=True)
class FocusOutcome:
    """The result of one focus check against being unsettled.

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
