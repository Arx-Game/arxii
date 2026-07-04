"""Constants for the ships system (#1832)."""

from django.db import models

# The Capability "kind" name ships register under, and the speed Capability
# name a ship's engine/rigging grants — see world/properties_capabilities for
# the shared Property/Capability substrate ships plug into.
SHIP_KIND_NAME = "Vessel"
SPEED_CAPABILITY_NAME = "speed"

# PLACEHOLDER tuning knobs — revisit once ship balance is playtested.
DAMAGED_HULL_DISCOUNT: int = 2
HANDLING_PER_LEVEL: int = 5
ARMAMENT_PER_LEVEL: int = 5

# PLACEHOLDER construction defaults. A ship isn't sized/graded the way a House
# is (BuildingSizeTier doesn't apply), but Building.target_size/target_grandeur/
# space_budget are all NOT NULL — these satisfy that shape until a ship-specific
# sizing system lands.
SHIP_BUILDING_TARGET_SIZE: int = 1
SHIP_BUILDING_TARGET_GRANDEUR: int = 1
SHIP_BUILDING_SPACE_BUDGET: int = 250
SHIP_CONSTRUCTION_THRESHOLD: int = 1000
SHIP_UPGRADE_THRESHOLD_PER_LEVEL: int = 100
SHIP_REPAIR_THRESHOLD: int = 200


class ShipUpgradeStat(models.TextChoices):
    """Which stat a persistent ship upgrade improves."""

    HANDLING = "handling", "Handling"
    ARMAMENT = "armament", "Armament"
