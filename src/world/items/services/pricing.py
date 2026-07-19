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

    For a **gem** (an instance with a ``GemInstanceDetails`` sidecar, Build 0b), worth
    is ``template.value × size × purity × cut`` — the gem grade multipliers replace the
    quality-tier multiplier. Otherwise: ``template.value`` scaled by the item's quality
    tier's ``stat_multiplier``. Either way, material construction value (``lore_value``)
    is added on top.
    """
    material = instance.lore_value or 0
    gem = instance.gem_or_none
    if gem is not None:
        from world.items.gems.services import compute_gem_worth  # noqa: PLC0415

        return compute_gem_worth(gem) + material
    base = instance.template.value
    tier = instance.quality_tier
    # ``stat_multiplier`` is a DecimalField but can be a plain float in memory
    # (unsaved/factory-built rows); wrap in Decimal(str(...)) as the rest of the
    # codebase does (ItemInstance.quality_multiplier) so ``Decimal * float`` never
    # raises TypeError.
    multiplier = Decimal(str(tier.stat_multiplier)) if tier is not None else Decimal(1)
    return int((Decimal(base) * multiplier).to_integral_value()) + material
