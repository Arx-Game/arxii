"""Appraisal — a crafted item's suggested economic worth (#2243).

Quality tier and material construction value now feed a price signal, so fine
goods are worth more than shoddy ones. This is a *suggestion* for market
pricing, never an enforced price — sellers still set their own numbers.
Magnitudes are PLACEHOLDER.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.items.models import ItemInstance


def appraise(instance: ItemInstance) -> int:
    """Estimate an item's worth in coppers (#2243).

    ``template.value`` scaled by the item's quality tier's ``stat_multiplier``,
    plus its material construction value (``lore_value``). A shoddy item is worth
    its base; a masterwork is worth a multiple; rich materials add on top.
    """
    base = instance.template.value
    tier = instance.quality_tier
    multiplier = tier.stat_multiplier if tier is not None else Decimal(1)
    material = instance.lore_value or 0
    return int((Decimal(base) * multiplier).to_integral_value()) + material
