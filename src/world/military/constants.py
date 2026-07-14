"""Constants for the military system.

Re-exports battle-side constants that MilitaryUnit shares, so the military
app doesn't depend on the battles app for enum/constant definitions.
"""

from __future__ import annotations

from world.battles.constants import (
    DEFAULT_MORALE,
    UnitQuality,
)

__all__ = ["DEFAULT_MORALE", "UnitQuality"]
