"""Compatibility facade for ``world.seeds.game_content.challenges`` (roadmap 3.2, #1220).

Content relocated there; this module re-exports every name so existing
``integration_tests.game_content.challenges`` imports in the test suite keep
working unchanged. New code should import from ``world.seeds.game_content.challenges``.
"""

from world.seeds.game_content.challenges import (
    APPLICATION_DEFS,
    BONUS_CONDITIONS,
    CAPABILITY_TYPES,
    CHALLENGE_BONUS_CONDITIONS,
    CHALLENGE_CATEGORIES,
    CHALLENGE_CHECK_TYPES,
    CHALLENGE_DEFS,
    PROPERTY_CATEGORIES,
    TRAIT_DERIVATIONS,
    ChallengeContent,
    ChallengeContentResult,
)

__all__ = [
    "APPLICATION_DEFS",
    "BONUS_CONDITIONS",
    "CAPABILITY_TYPES",
    "CHALLENGE_BONUS_CONDITIONS",
    "CHALLENGE_CATEGORIES",
    "CHALLENGE_CHECK_TYPES",
    "CHALLENGE_DEFS",
    "PROPERTY_CATEGORIES",
    "TRAIT_DERIVATIONS",
    "ChallengeContent",
    "ChallengeContentResult",
]
