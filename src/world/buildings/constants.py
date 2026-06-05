"""Constants for the buildings system."""

from django.db import models


class PermitEligibility(models.TextChoices):
    """How a ward decides who can build there."""

    OPEN = "open", "Open — anyone with a permit"
    REPUTATION_GATED = "reputation_gated", "Reputation gated — minimum standing required"
    NPC_CONTROLLED = "npc_controlled", "NPC controlled — only via specific NPC's authority"
    CLOSED = "closed", "Closed — no permits issued"


# Quality / size / grandeur knobs use simple integer ranges (1-10) rather
# than TextChoices — the naming problem at 10 tiers is unsolvable, staff
# can author per-kind UI labels for tier names if they want.
TARGET_SIZE_MIN = 1
TARGET_SIZE_MAX = 10
TARGET_GRANDEUR_MIN = 1
TARGET_GRANDEUR_MAX = 10


# #676 Phase E — Polish upkeep decay constants.
#
# Cron fires once per RL week. When upkeep is missed on a building,
# decay proceeds outermost-first: the lowest-priority active
# BuildingProjectInstance accumulates ``consecutive_missed_upkeep``
# ticks; its polish drops each tick by ``DECAY_BASE_AMOUNT ×
# (DECAY_ACCELERATION_FACTOR ** (ticks - 1))``. When the instance's
# polish hits 0, decay moves to the next-priority instance (which
# starts at tick 1 fresh).
#
# A successful weekly payment resets ``consecutive_missed_upkeep`` to 0
# on every instance of that building — the building-as-whole is the
# unit of maintenance.
DECAY_BASE_AMOUNT: int = 50
DECAY_ACCELERATION_FACTOR: float = 1.5

# Mass Feature Restoration project cost is ~10% of the summed original
# polish costs across decayed instances. The full Restoration Project
# clears dormancy; mass-restoration refills polish on already-restored
# buildings.
MASS_RESTORATION_COST_FRACTION: float = 0.10
