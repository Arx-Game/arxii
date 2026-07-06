"""Compatibility facade for ``world.seeds.game_content.characters`` (roadmap 3.2, #1220).

Content relocated there; this module re-exports every name so existing
``integration_tests.game_content.characters`` imports in the test suite keep
working unchanged. New code should import from ``world.seeds.game_content.characters``.
"""

from world.seeds.game_content.characters import (
    _CHALLENGE_STAT_NAMES,
    _CHALLENGE_TRAIT_VALUE,
    _SOCIAL_STAT_NAMES,
    _SOCIAL_TRAIT_VALUE,
    CharacterContent,
)

__all__ = [
    "_CHALLENGE_STAT_NAMES",
    "_CHALLENGE_TRAIT_VALUE",
    "_SOCIAL_STAT_NAMES",
    "_SOCIAL_TRAIT_VALUE",
    "CharacterContent",
]
