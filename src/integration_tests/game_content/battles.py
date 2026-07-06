"""Compatibility facade for ``world.seeds.game_content.battles`` (roadmap 3.2, #1220).

Content relocated there; this module re-exports every name so existing
``integration_tests.game_content.battles`` imports in the test suite keep
working unchanged. New code should import from ``world.seeds.game_content.battles``.
"""

from world.seeds.game_content.battles import (
    seed_champion_duel_outcome_wiring,
)

__all__ = [
    "seed_champion_duel_outcome_wiring",
]
