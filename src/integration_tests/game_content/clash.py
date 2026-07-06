"""Compatibility facade for ``world.seeds.game_content.clash`` (roadmap 3.2, #1220).

Content relocated there; this module re-exports every name so existing
``integration_tests.game_content.clash`` imports in the test suite keep
working unchanged. New code should import from ``world.seeds.game_content.clash``.
"""

from world.seeds.game_content.clash import (
    ClashContent,
    ClashContentResult,
    _add_minimal_pool_entry,
    _ensure_combo_slots,
)

__all__ = [
    "ClashContent",
    "ClashContentResult",
    "_add_minimal_pool_entry",
    "_ensure_combo_slots",
]
