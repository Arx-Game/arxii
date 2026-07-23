"""Compatibility facade for ``world.seeds.game_content.items`` (roadmap 3.2, #1220).

Content relocated there; this module re-exports every name so existing
``integration_tests.game_content.items`` imports in the test suite keep
working unchanged. New code should import from ``world.seeds.game_content.items``.
"""

from world.seeds.game_content.items import (
    ItemsDevSeedResult,
    ItemTemplateStarterCatalogResult,
    _build_template_specs,
    seed_item_template_starter_catalog,
    seed_items_dev,
)

__all__ = [
    "ItemTemplateStarterCatalogResult",
    "ItemsDevSeedResult",
    "_build_template_specs",
    "seed_item_template_starter_catalog",
    "seed_items_dev",
]
