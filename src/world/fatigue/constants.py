from django.db import models


class FatigueCategory(models.TextChoices):
    PHYSICAL = "physical", "Physical"
    SOCIAL = "social", "Social"
    MENTAL = "mental", "Mental"


class FatigueZone(models.TextChoices):
    FRESH = "fresh", "Fresh"
    STRAINED = "strained", "Strained"
    TIRED = "tired", "Tired"
    OVEREXERTED = "overexerted", "Overexerted"
    EXHAUSTED = "exhausted", "Exhausted"


class EffortLevel(models.TextChoices):
    HALFHEARTED = "halfhearted", "Halfhearted"
    NORMAL = "normal", "Normal"
    ALL_OUT = "all_out", "All Out"


# Zone thresholds (percentage of capacity)
ZONE_THRESHOLDS = [
    (FatigueZone.FRESH, 0, 40),
    (FatigueZone.STRAINED, 41, 60),
    (FatigueZone.TIRED, 61, 80),
    (FatigueZone.OVEREXERTED, 81, 99),
    (FatigueZone.EXHAUSTED, 100, None),
]

# Check penalties per zone
ZONE_PENALTIES = {
    FatigueZone.FRESH: 0,
    FatigueZone.STRAINED: -1,
    FatigueZone.TIRED: -2,
    FatigueZone.OVEREXERTED: -3,
    FatigueZone.EXHAUSTED: -4,
}

# Effort modifiers
EFFORT_CHECK_MODIFIER = {
    EffortLevel.HALFHEARTED: -2,
    EffortLevel.NORMAL: 0,
    EffortLevel.ALL_OUT: 2,
}

EFFORT_COST_MULTIPLIER = {
    EffortLevel.HALFHEARTED: 0.3,
    EffortLevel.NORMAL: 1.0,
    EffortLevel.ALL_OUT: 2.0,
}

# Capacity formula constants
CAPACITY_STAT_MULTIPLIER = 10
CAPACITY_WILLPOWER_MULTIPLIER = 3
WELL_RESTED_MULTIPLIER = 1.5

# Rest command
REST_AP_COST = 10

# Endurance stat per fatigue category
FATIGUE_ENDURANCE_STAT = {
    FatigueCategory.PHYSICAL: "stamina",
    FatigueCategory.SOCIAL: "composure",
    FatigueCategory.MENTAL: "stability",
}
