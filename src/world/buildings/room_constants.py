"""Constants for the Room Builder (#670)."""

from __future__ import annotations

from typing import NamedTuple


class Direction(NamedTuple):
    """A dig direction: coordinate delta, reverse name, and telnet aliases."""

    dx: int
    dy: int
    dfloor: int
    opposite: str
    aliases: tuple[str, ...]


# North renders as +y (maps draw +y upward). Up/down move floors, not cells.
DIRECTIONS: dict[str, Direction] = {
    "north": Direction(0, 1, 0, "south", ("n",)),
    "south": Direction(0, -1, 0, "north", ("s",)),
    "east": Direction(1, 0, 0, "west", ("e",)),
    "west": Direction(-1, 0, 0, "east", ("w",)),
    "northeast": Direction(1, 1, 0, "southwest", ("ne",)),
    "northwest": Direction(-1, 1, 0, "southeast", ("nw",)),
    "southeast": Direction(1, -1, 0, "northwest", ("se",)),
    "southwest": Direction(-1, -1, 0, "northeast", ("sw",)),
    "up": Direction(0, 0, 1, "down", ("u",)),
    "down": Direction(0, 0, -1, "up", ("d",)),
}

UNFINISHED_ROOM_DESC = "An unfinished room."  # PLACEHOLDER

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
