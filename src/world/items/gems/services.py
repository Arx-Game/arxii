"""Gem worth computation (Build 0b slice 1)."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.items.gems.models import GemInstanceDetails


def compute_gem_worth(gem: GemInstanceDetails) -> int:
    """Return a gem's worth in coppers: ``template.value × size × purity × cut``.

    The base value comes from the gem *type* (``ItemTemplate.value``, set by the
    type's quality level); the three grade multipliers scale it. Rounded to a whole
    copper. Consumed by ``world.items.services.pricing.appraise`` for gem instances.
    """
    base = gem.item_instance.template.value
    factor = (
        Decimal(str(gem.size_grade.multiplier))
        * Decimal(str(gem.purity_grade.multiplier))
        * Decimal(str(gem.cut_grade.multiplier))
    )
    return int((Decimal(base) * factor).to_integral_value())
