from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.magic.models.affinity import Affinity
    from world.magic.models.aura import CharacterAura


@dataclass(frozen=True)
class AffinityShare:
    """One affinity's percentage of an aura."""

    affinity: Affinity
    percent: Decimal


@dataclass(frozen=True)
class AuraPercentages:
    """An aura's percentages, one share per affinity the character holds."""

    shares: tuple[AffinityShare, ...]

    def percent_for(self, affinity: Affinity) -> Decimal:
        """This affinity's percent, 0 when the aura holds no share of it."""
        for share in self.shares:
            if share.affinity.pk == affinity.pk:
                return share.percent
        return Decimal(0)


@dataclass(frozen=True)
class AuraDrift:
    """Before/after aura percentages from one recompute_aura() call."""

    before: AuraPercentages
    after: AuraPercentages


@dataclass(frozen=True)
class ActingAura:
    """The aura a character acts with right now.

    An active alternate self whose resonance names an affinity acts as 100% of
    that affinity; otherwise the character's true ``CharacterAura`` applies.
    Read-only view: the true aura is never altered by an alternate self.
    """

    true_aura: CharacterAura | None
    alternate_affinity: Affinity | None = None

    @property
    def is_alternate_self(self) -> bool:
        """True when an active alternate self's resonance replaces the true aura."""
        return self.alternate_affinity is not None

    @property
    def has_shares(self) -> bool:
        """True when this aura holds at least one affinity share."""
        if self.alternate_affinity is not None:
            return True
        return self.true_aura is not None and bool(self.true_aura.cached_shares)

    def percent_for(self, affinity: Affinity) -> Decimal:
        """This affinity's percent of the acting aura; 0 when it holds none."""
        if self.alternate_affinity is not None:
            if self.alternate_affinity.pk == affinity.pk:
                return Decimal(100)
            return Decimal(0)
        if self.true_aura is None:
            return Decimal(0)
        return self.true_aura.percent_for(affinity)

    @property
    def dominant_affinity(self) -> Affinity | None:
        """The leading affinity, or None when the aura holds no shares."""
        if self.alternate_affinity is not None:
            return self.alternate_affinity
        if self.true_aura is None or not self.true_aura.cached_shares:
            return None
        return self.true_aura.dominant_affinity
