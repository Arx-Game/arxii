"""Crafting submodule for the items app.

Provides the generic magical-crafting framework: recipes, ingredient slots,
attempt tracking, and cost consumption. All models carry ``Meta.app_label = "items"``
so Django discovers them under the ``items`` app label.
"""

# Register concrete handlers at package import time so that
# ``get_handler(CraftingRecipeKind.FACET_ATTACH)`` works as soon as
# ``world.items.crafting`` is imported.
import world.items.crafting.handlers  # noqa: F401
