"""Constants for the Room Builder (#670).

``Direction``/``DIRECTIONS`` and ``UNFINISHED_ROOM_DESC`` moved to
``world.areas.constants`` (#3269) so the staff world builder shares them
without inverting the areas←buildings layering; re-exported here for
existing consumers.
"""

from __future__ import annotations

from world.areas.constants import (  # noqa: F401
    DIRECTIONS,
    UNFINISHED_ROOM_DESC,
    Direction,
)

# PLACEHOLDER — economy pass tunes. Contribution progress divides money by 100
# (projects.services), so threshold-per-unit 100 ≈ 10,000 money per budget unit.
EXTENSION_THRESHOLD_PER_UNIT = 100

# Fortification investment (#1713). Bounded ladder — see BASE_INTEGRITY/
# FORTIFICATION_LEVEL_INTEGRITY_BONUS in world.battles.constants for why an
# uncapped level would make a structure unbreachable. PLACEHOLDER threshold
# pending the economy pass (mirrors EXTENSION_THRESHOLD_PER_UNIT above).
MAX_FORTIFICATION_LEVEL = 5
FORTIFICATION_UPGRADE_THRESHOLD_PER_LEVEL = 150

# Building renovation (#1858). Re-points a Building to a different
# admin-authored BuildingKind on completion, changing its flag set. Flat
# PLACEHOLDER threshold pending the economy pass (renovations don't scale
# by units/levels like extension/fortification; a single reclassification cost).
RENOVATION_THRESHOLD = 150

# Building upgrade (#1888). Bumps Building.target_size up to a higher tier
# and re-snapshots space_budget from BuildingSizeTier. PLACEHOLDER threshold
# per tier pending the economy pass — larger than EXTENSION_THRESHOLD_PER_UNIT
# (a size-tier bump grows the budget more than a flat-budget extension).
MAX_BUILDING_SIZE_TIER = 7
UPGRADE_THRESHOLD_PER_TIER = 200
