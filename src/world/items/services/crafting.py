"""Services: check-driven facet crafting (Spec D PR2 / #510)."""

from __future__ import annotations

from world.items.models import FacetCraftingConfig


def get_facet_crafting_config() -> FacetCraftingConfig:
    """Lazy-create and return the singleton crafting config (pk=1)."""
    config, _ = FacetCraftingConfig.objects.get_or_create(pk=1)
    return config
