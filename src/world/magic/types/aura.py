from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.magic.models.affinity import Affinity


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
