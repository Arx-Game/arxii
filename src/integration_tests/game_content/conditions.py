"""Compatibility facade for ``world.seeds.game_content.conditions`` (roadmap 3.2, #1220).

Content relocated there; this module re-exports every name so existing
``integration_tests.game_content.conditions`` imports in the test suite keep
working unchanged. New code should import from ``world.seeds.game_content.conditions``.
"""

from world.seeds.game_content.conditions import (
    _SOCIAL_CONDITIONS,
    CAPTIVATED,
    CHARMED,
    DECEIVED,
    ENTHRALLED,
    SHAKEN,
    SMITTEN,
    ConditionContent,
)

__all__ = [
    "CAPTIVATED",
    "CHARMED",
    "DECEIVED",
    "ENTHRALLED",
    "SHAKEN",
    "SMITTEN",
    "_SOCIAL_CONDITIONS",
    "ConditionContent",
]
