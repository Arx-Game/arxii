"""Power-tier helpers for Court gulf enforcement (#1589).

Public API
----------
- power_tier_for_level(level: int) -> int
"""

import math

from world.progression.models.unlocks import TIER_ONE_MAX_LEVEL


def power_tier_for_level(level: int) -> int:
    """Return the power tier for a given character level.

    Tier 1 covers levels 1-TIER_ONE_MAX_LEVEL, tier 2 the next band, etc.
    Levels ≤ 0 are treated as tier 1 (min tier is always 1).

    >>> power_tier_for_level(0)
    1
    >>> power_tier_for_level(1)
    1
    >>> power_tier_for_level(5)
    1
    >>> power_tier_for_level(6)
    2
    >>> power_tier_for_level(10)
    2
    >>> power_tier_for_level(11)
    3
    """
    return max(1, math.ceil(level / TIER_ONE_MAX_LEVEL))
