"""Constants for the justice app — heat tiers, decay, default law posture (#1765).

All magnitudes and the intermediate tier names are PLACEHOLDER pending the
tuning/naming pass.
"""

from django.db import models

# PLACEHOLDER magnitudes (tuning pass pending).
DEFAULT_HEAT_WEIGHT = 10
HEAT_DECAY_PER_DAY = 5


class HeatTier(models.TextChoices):
    """Player-facing pursuit ratings, colour-coded — never a raw number.

    SAFE / HEAT_IS_ON / EXTREME_HEAT names are user-ratified endpoints; the
    intermediate names are PLACEHOLDER.
    """

    SAFE = "safe", "Safe"
    WATCHED = "watched", "Watched"  # PLACEHOLDER name
    HUNTED = "hunted", "Hunted"  # PLACEHOLDER name
    HEAT_IS_ON = "heat_is_on", "The Heat Is On"
    EXTREME_HEAT = "extreme_heat", "Extreme Heat"


# Ascending (tier, minimum value) ladder; PLACEHOLDER thresholds.
HEAT_TIER_FLOORS: tuple[tuple[HeatTier, int], ...] = (
    (HeatTier.EXTREME_HEAT, 100),
    (HeatTier.HEAT_IS_ON, 60),
    (HeatTier.HUNTED, 25),
    (HeatTier.WATCHED, 1),
    (HeatTier.SAFE, 0),
)


def tier_for_value(value: int) -> HeatTier:
    """Map a summed heat value onto its display tier."""
    for tier, floor in HEAT_TIER_FLOORS:
        if value >= floor:
            return tier
    return HeatTier.SAFE
