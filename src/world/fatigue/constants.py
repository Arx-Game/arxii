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
    VERY_LOW = "very_low", "Very Low Effort"
    LOW = "low", "Low Effort"
    MEDIUM = "medium", "Medium Effort"
    HIGH = "high", "High Effort"
    EXTREME = "extreme", "Extreme Effort"


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

# Effort check modifiers (added to check result)
EFFORT_CHECK_MODIFIER = {
    EffortLevel.VERY_LOW: -3,
    EffortLevel.LOW: -1,
    EffortLevel.MEDIUM: 0,
    EffortLevel.HIGH: 2,
    EffortLevel.EXTREME: 4,
}

# Effort fatigue cost multipliers (applied to base action cost)
EFFORT_COST_MULTIPLIER = {
    EffortLevel.VERY_LOW: 0.1,  # Virtually free (1 fatigue minimum)
    EffortLevel.LOW: 0.5,
    EffortLevel.MEDIUM: 1.0,
    EffortLevel.HIGH: 2.0,
    EffortLevel.EXTREME: 3.5,  # Very expensive — can cause quick collapse
}

# Minimum fatigue cost (even very low effort costs at least 1)
MIN_FATIGUE_COST = 1

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

# Collapse risk zones per effort level. Maps effort → minimum zone where collapse triggers.
# VERY_LOW and LOW never trigger collapse. MEDIUM only at EXHAUSTED. HIGH/EXTREME at OVEREXERTED+.
COLLAPSE_RISK_ZONES: dict[str, FatigueZone | None] = {
    EffortLevel.VERY_LOW: None,  # Never collapses
    EffortLevel.LOW: None,  # Never collapses
    EffortLevel.MEDIUM: FatigueZone.EXHAUSTED,  # Only when past 100%
    EffortLevel.HIGH: FatigueZone.OVEREXERTED,  # 81%+
    EffortLevel.EXTREME: FatigueZone.OVEREXERTED,  # 81%+
}
