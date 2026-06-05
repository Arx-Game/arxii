"""Constants for the societies system.

Currently houses the Renown system constants (#676 Phase A). Other shared
society / org / reputation primitives live in models.py alongside their
field definitions for historical reasons.
"""

from django.db import models

# ---------------------------------------------------------------------------
# Fame tier ladder (Renown system, #676)
#
# Fame is a per-persona accumulating buffer with cron decay (5 + 5%/IC day).
# The five tiers are derived display labels — the persona's fame_tier field
# stores the tier name as a CharField, recomputed on every fame_points write.
# Tier multipliers are NOT stored on the persona; they're applied at display
# time by viewer-facing code.
# ---------------------------------------------------------------------------


class FameTier(models.TextChoices):
    """Derived fame tier labels for the Renown system.

    The persona's ``fame_tier`` field stores one of these values. The numeric
    threshold and multiplier are looked up from ``FAME_TIER_THRESHOLDS`` and
    ``FAME_TIER_MULTIPLIERS`` at tier-derivation and display time respectively.
    """

    NORMAL = "normal", "Normal"
    TALKED_ABOUT = "talked_about", "Talked About"
    CELEBRITY = "celebrity", "Celebrity"
    HOUSEHOLD_NAME = "household_name", "Household Name"
    WORLD_FAMOUS = "world_famous", "World Famous"


# Minimum fame_points required to enter each tier. Floors at NORMAL = 0.
# Admin-tunable via a future settings model; hard-coded for now.
FAME_TIER_THRESHOLDS: dict[str, int] = {
    FameTier.NORMAL.value: 0,
    FameTier.TALKED_ABOUT.value: 100,
    FameTier.CELEBRITY.value: 1_000,
    FameTier.HOUSEHOLD_NAME.value: 10_000,
    FameTier.WORLD_FAMOUS.value: 100_000,
}

# Multiplier applied to total_prestige to compute displayed prestige when this
# tier is active. Admin-tunable via a future settings model.
FAME_TIER_MULTIPLIERS: dict[str, float] = {
    FameTier.NORMAL.value: 1.0,
    FameTier.TALKED_ABOUT.value: 1.25,
    FameTier.CELEBRITY.value: 2.5,
    FameTier.HOUSEHOLD_NAME.value: 5.0,
    FameTier.WORLD_FAMOUS.value: 10.0,
}

# Ordered tier list from lowest to highest. Used by the tier-derivation
# service to walk thresholds in order.
FAME_TIER_ORDER: tuple[str, ...] = (
    FameTier.NORMAL.value,
    FameTier.TALKED_ABOUT.value,
    FameTier.CELEBRITY.value,
    FameTier.HOUSEHOLD_NAME.value,
    FameTier.WORLD_FAMOUS.value,
)


# ---------------------------------------------------------------------------
# Decay rates (Renown system, #676)
#
# Fame decay is per IC day. With the canonical 3:1 IC:OOC time ratio
# (game_clock.GameClock.time_ratio default), 1 IC day == 8 real hours.
# The renown decay cron fires every 8 real hours.
#
# Formula: fame_new = max(0, fame_old - FAME_DECAY_FLAT - FAME_DECAY_PCT * fame_old)
#
# Half-life at high fame is dominated by the percentage term (~14 IC days
# = ~4.6 real days). At low fame the flat term drains the residue in
# ~3 weeks of real time.
# ---------------------------------------------------------------------------

FAME_DECAY_FLAT: int = 5
FAME_DECAY_PCT: float = 0.05

# Organization accumulated_prestige and accumulated_fame decay rates,
# matching the persona fame cadence and curve. accumulated_legend on
# covenants is permanent and never appears here.
ORG_PRESTIGE_DECAY_FLAT: int = 5
ORG_PRESTIGE_DECAY_PCT: float = 0.05
ORG_FAME_DECAY_FLAT: int = 5
ORG_FAME_DECAY_PCT: float = 0.05
