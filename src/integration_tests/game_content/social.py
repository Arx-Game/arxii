"""Compatibility facade for ``world.seeds.game_content.social`` (roadmap 3.2, #1220).

Content relocated there; this module re-exports every name so existing
``integration_tests.game_content.social`` imports in the test suite keep
working unchanged. New code should import from ``world.seeds.game_content.social``.
"""

from world.seeds.game_content.social import (
    ACTION_CONDITION_MAP,
    SocialContent,
    SocialContentResult,
)

__all__ = [
    "ACTION_CONDITION_MAP",
    "SocialContent",
    "SocialContentResult",
]
