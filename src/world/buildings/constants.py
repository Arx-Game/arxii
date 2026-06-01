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
