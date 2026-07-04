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


class ShipUpgradeStat(models.TextChoices):
    """Which stat a persistent ship upgrade improves."""

    HANDLING = "handling", "Handling"
    ARMAMENT = "armament", "Armament"
