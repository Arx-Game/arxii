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


# #1930 — Condition-tier ladder.
#
# A building's condition is a discrete tier (qualitative label player-facing,
# per ADR-0031's fiction-label rule), NOT a continuously creeping percentage —
# tiers give visible grace time instead of always-logged-in pressure.
# EXCELLENT is *normal*: ordinary paid upkeep holds it forever. Tiers above
# EXCELLENT are reached only via preparation projects and decay back on a
# short dwell timer; tiers below are reached only through sustained missed
# upkeep (arrears accrue first) and floor at DECAYED — nonpayment never
# mutates polish/feature rows (regress, never destroy).
class ConditionTier(models.IntegerChoices):
    """Building condition ladder. Labels are PLACEHOLDER fiction prose."""

    DECAYED = 0, "Decayed"
    RAMSHACKLE = 1, "Ramshackle"
    WORN = 2, "Worn"
    FINE = 3, "Fine"
    GOOD = 4, "Good"
    EXCELLENT = 5, "Excellent"
    EXTRAVAGANT = 6, "Extravagantly Polished"
    IMMACULATE = 7, "Immaculate"


# Percent multiplier applied to the building-derived prestige component.
# A step function of tier — deliberately not continuous. PLACEHOLDER.
CONDITION_PRESTIGE_MULTIPLIER: dict[int, int] = {
    ConditionTier.DECAYED: 5,
    ConditionTier.RAMSHACKLE: 20,
    ConditionTier.WORN: 40,
    ConditionTier.FINE: 60,
    ConditionTier.GOOD: 80,
    ConditionTier.EXCELLENT: 100,
    ConditionTier.EXTRAVAGANT: 150,
    ConditionTier.IMMACULATE: 200,
}

# Above-normal tiers decay one step once this dwell lapses (checked by the
# weekly sweep). IMMACULATE can be held past the dwell only while the owner
# pays the ultra-upkeep premium. PLACEHOLDER.
ABOVE_NORMAL_DWELL_DAYS: int = 7

# Misses accrue arrears silently for this many weeks before condition
# starts sliding (grace time), then one tier per SLIP_WEEKS_PER_TIER
# further missed weeks. Arrears cap at ARREARS_CAP_WEEKS × weekly cost —
# absence is never punished beyond a bounded bill. PLACEHOLDER.
GRACE_MISSES: int = 2
SLIP_WEEKS_PER_TIER: int = 4
ARREARS_CAP_WEEKS: int = 8

# Consecutive paid weeks needed to climb one tier back toward EXCELLENT
# (refurbishment is the fast path). PLACEHOLDER.
REGAIN_WEEKS_PER_TIER: int = 2

# Ultra upkeep: premium charged on top of normal upkeep to hold IMMACULATE
# past its dwell — an outrageous recurring spend, not a default. PLACEHOLDER.
ULTRA_UPKEEP_MULTIPLIER: int = 4

# Priced recovery (coppers, scaled by Building.target_size). Refurbish
# restores to EXCELLENT. ("Renovation" is the existing kind-swap project —
# different verb on purpose.) PLACEHOLDER pending the economy pass.
REFURBISH_COPPER_PER_TIER: int = 500

# Grand Preparation (#1930, Apostate 2026-07-06): pushing above EXCELLENT is
# a small funded project, not an instant purchase. Its cost is a proportion
# of the house's base prestige (you're buying extra shine on what the house
# already is), with a floor for low-polish houses; the project threshold is
# funded in coppers (1 progress per 100c, the standard pipe) and can be sped
# along with AP Household Command checks. PLACEHOLDER.
PREPARE_COST_PERCENT_OF_PRESTIGE: dict[int, int] = {
    ConditionTier.EXTRAVAGANT: 25,
    ConditionTier.IMMACULATE: 50,
}
PREPARE_COST_FLOOR_COPPERS: dict[int, int] = {
    ConditionTier.EXTRAVAGANT: 2000,
    ConditionTier.IMMACULATE: 5000,
}
PREPARATION_PROJECT_DAYS: int = 30

# Shared by Grand Preparation (condition_services.prepare_cost) and the
# BUILDING_ACTIVATION project kind (property_grant_services) — coppers
# funded per unit of Project progress.
COPPERS_PER_PROGRESS_POINT = 100
