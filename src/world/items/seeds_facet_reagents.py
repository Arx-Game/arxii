"""Seed CraftingMaterialRequirement content for FACET_ATTACH (#707).

No service-layer change needed here — run_crafting_recipe() already stages
and consumes CraftingMaterialRequirement rows generically for every
CraftingRecipeKind (world/items/crafting/cost.py: stage_and_assert_affordable
/ consume_cost). This is content-only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.items.models import CraftingMaterialRequirement, ItemTemplate

if TYPE_CHECKING:
    from world.items.crafting.models import CraftingRecipe


def ensure_facet_attach_reagent_requirement(recipe: CraftingRecipe) -> ItemTemplate:
    """Get-or-create a generic reagent template + its requirement row on ``recipe``."""
    template, _ = ItemTemplate.objects.get_or_create(
        name="Enchanter's Binding Thread",
        defaults={
            "description": "A fine thread used to bind a facet's meaning into an item.",
            "weight": 0.05,
            "size": 1,
            "value": 0,
        },
    )
    CraftingMaterialRequirement.objects.get_or_create(
        recipe=recipe, item_template=template, defaults={"quantity": 1}
    )
    return template
