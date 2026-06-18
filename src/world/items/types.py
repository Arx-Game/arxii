"""Type definitions for the items app."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.checks.types import CheckResult
    from world.items.models import ItemFacet, ItemStyle, QualityTier
    from world.mechanics.types import AppliedEffect
    from world.traits.models import CheckOutcome


@dataclass(frozen=True)
class FacetCraftResult:
    """Outcome of a facet-crafting attempt."""

    attached: bool
    outcome: CheckOutcome | None
    item_facet: ItemFacet | None
    quality_tier: QualityTier | None


@dataclass(frozen=True)
class StyleCraftResult:
    """Outcome of a style-crafting attempt."""

    attached: bool
    outcome: CheckOutcome | None
    item_style: ItemStyle | None
    quality_tier: QualityTier | None


@dataclass(frozen=True)
class UseItemResult:
    """Outcome of using an item: effects applied, charges left, destruction."""

    applied_effects: list[AppliedEffect] = field(default_factory=list)
    charges_remaining: int = 0
    destroyed: bool = False
    soft_deleted: bool = False
    check_result: CheckResult | None = None
