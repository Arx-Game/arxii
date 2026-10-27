"""Result types for burning resonance as a Strain option (#4736)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from decimal import Decimal

    from world.checks.types import CheckResult
    from world.magic.models import Resonance


@dataclass(frozen=True)
class BurnValuation:
    """What a number of burned points is worth to one caster.

    ``valued_points`` are the points after a hasty fall's conversion at the Fall pair
    rate (equal to the burned points otherwise). ``strain_units`` are what enter the
    strain curve beside the anima strain. ``hasty_fall`` is True when an Abyssal caster
    burned Celestial or Primal resonance: the points were valued as Abyssal and the
    cast's corruption for them is multiplied.
    """

    points: int
    valued_points: int
    strain_units: int
    hasty_fall: bool


@dataclass(frozen=True)
class ResonanceBurnResult:
    """The resolved burn for one action: requested, capped, rolled and reached.

    ``capped`` is the request after the intensity ceiling and the balance left once
    the pull's own cost is paid. ``reached`` is ``reach_percent`` of ``capped`` and is
    the only amount debited. ``check_result`` is None when nothing could be reached
    (a zero cap), so no check was rolled.
    """

    resonance: Resonance
    requested: int
    ceiling: int
    capped: int
    reach_percent: int
    reached: int
    valuation: BurnValuation
    check_result: CheckResult | None = None

    @property
    def strain_units(self) -> int:
        return self.valuation.strain_units

    @property
    def hasty_fall(self) -> bool:
        return self.valuation.hasty_fall


@dataclass(frozen=True)
class BurnPreview:
    """The burn numbers the pull preview shows before anything is committed.

    ``ceiling`` is the most she may burn now: the intensity ceiling, capped by the
    balance left after the pull's cost. ``strain_units_per_point`` is what one burned
    point is worth to her for this resonance (after a hasty fall's conversion).
    ``available`` is False when no strain check is designated, so a burn would be
    refused.
    """

    ceiling: int
    strain_units_per_point: Decimal
    hasty_fall: bool
    available: bool
