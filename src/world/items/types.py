"""Type definitions for the items app."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.items.models import ItemFacet, QualityTier
    from world.traits.models import CheckOutcome


@dataclass(frozen=True)
class FacetCraftResult:
    """Outcome of a facet-crafting attempt."""

    attached: bool
    outcome: CheckOutcome | None
    item_facet: ItemFacet | None
    quality_tier: QualityTier | None
