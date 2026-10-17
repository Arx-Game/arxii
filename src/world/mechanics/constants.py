"""Constants for the mechanics system."""

from django.db import models

# Re-export from checks app for backwards compatibility
from world.checks.constants import EffectTarget, EffectType  # noqa: F401

# ModifierCategory name constants (must match fixture data)
STAT_CATEGORY_NAME = "stat"
GOAL_CATEGORY_NAME = "goal"
GOAL_PERCENT_CATEGORY_NAME = "goal_percent"
GOAL_POINTS_CATEGORY_NAME = "goal_points"
RESONANCE_CATEGORY_NAME = "resonance"
CHECK_CATEGORY_NAME = "check"
POWER_CATEGORY_NAME = "power"
POWER_MULTIPLIER_TARGET_NAME = "power_multiplier"
# #2643 — the bounded team-damage-percent lane's ModifierTarget name (same "power"
# category as power_multiplier, but read/clamped SEPARATELY — see
# world.magic.services.techniques._apply_power_multiplier_stage / ADR-0158).
TEAM_DAMAGE_PERCENT_TARGET_NAME = "team_damage_percent"
TECHNIQUE_STAT_CATEGORY_NAME = "technique_stat"
TECHNIQUE_STAT_INTENSITY = "intensity"
TECHNIQUE_STAT_CONTROL = "control"
# #4333 — favor with a being. Each being has one target in each category
# (ModifierTarget.target_being), plus one "any being" target per category.
# favor_invocation values are difficulty points eased on the invocation check;
# favor_earning values are percentage points added to the earning rate.
FAVOR_INVOCATION_CATEGORY_NAME = "favor_invocation"
FAVOR_EARNING_CATEGORY_NAME = "favor_earning"
FAVOR_CATEGORY_NAMES: frozenset[str] = frozenset(
    {FAVOR_INVOCATION_CATEGORY_NAME, FAVOR_EARNING_CATEGORY_NAME}
)
# #4394 — the five IC levers a distinction may pull (ruled allowed by ApostateCD
# 2026-09-07; XP and Kudos never). One category each, one reader each, through
# ``world.mechanics.levers``. Percent levers (income, reputation gain, relationship
# gain, fatigue cost) are integer percentage points on a computed amount, the
# ``favor_earning`` convention; comfort is a flat shift in comfort levels. Each
# category's target is named after the category; reputation gain also has one
# target per leg so a row can scale society regard or organization regard alone.
INCOME_CATEGORY_NAME = "income"
INCOME_TARGET_NAME = "income"
REPUTATION_GAIN_CATEGORY_NAME = "reputation_gain"
REPUTATION_GAIN_TARGET_NAME = "reputation_gain"
REPUTATION_GAIN_SOCIETY_TARGET_NAME = "reputation_gain_society"
REPUTATION_GAIN_ORGANIZATION_TARGET_NAME = "reputation_gain_organization"
RELATIONSHIP_GAIN_CATEGORY_NAME = "relationship_gain"
RELATIONSHIP_GAIN_TARGET_NAME = "relationship_gain"
COMFORT_CATEGORY_NAME = "comfort"
COMFORT_TARGET_NAME = "comfort"
FATIGUE_COST_CATEGORY_NAME = "fatigue_cost"
FATIGUE_COST_TARGET_NAME = "fatigue_cost"
# Sight through a mask (#4396): one target per ``DisguiseKind`` value (``world.forms``), named
# by the kind. A positive total on a kind's target lets the character see who is behind a
# disguise of that kind without the identification contest; the names are spelled here
# rather than imported because forms depends on mechanics, never the reverse.
DISGUISE_SIGHT_CATEGORY_NAME = "disguise_sight"
DISGUISE_SIGHT_TARGET_NAMES: tuple[str, ...] = ("mundane", "magical")
LEVER_TARGETS: tuple[tuple[str, str], ...] = (
    (INCOME_CATEGORY_NAME, INCOME_TARGET_NAME),
    (REPUTATION_GAIN_CATEGORY_NAME, REPUTATION_GAIN_TARGET_NAME),
    (REPUTATION_GAIN_CATEGORY_NAME, REPUTATION_GAIN_SOCIETY_TARGET_NAME),
    (REPUTATION_GAIN_CATEGORY_NAME, REPUTATION_GAIN_ORGANIZATION_TARGET_NAME),
    (RELATIONSHIP_GAIN_CATEGORY_NAME, RELATIONSHIP_GAIN_TARGET_NAME),
    (COMFORT_CATEGORY_NAME, COMFORT_TARGET_NAME),
    (FATIGUE_COST_CATEGORY_NAME, FATIGUE_COST_TARGET_NAME),
    *((DISGUISE_SIGHT_CATEGORY_NAME, name) for name in DISGUISE_SIGHT_TARGET_NAMES),
)

# ModifierSource.source_type return values
SOURCE_TYPE_DISTINCTION = "distinction"
SOURCE_TYPE_RESIDENCE_COMFORT = "residence_comfort"
SOURCE_TYPE_ACHIEVEMENT_REWARD = "achievement_reward"
SOURCE_TYPE_UNKNOWN = "unknown"
SOURCE_TYPE_FORM = "form"


class ChallengeType(models.TextChoices):
    """Whether a challenge blocks actions or actively causes harm."""

    INHIBITOR = "inhibitor", "Inhibitor (blocks actions/progress)"
    THREAT = "threat", "Threat (actively causes harm)"


class DiscoveryType(models.TextChoices):
    """Whether a challenge approach is immediately visible or must be discovered."""

    OBVIOUS = "obvious", "Obvious (visible if capability met)"
    DISCOVERABLE = "discoverable", "Discoverable (must be learned)"


class ResolutionType(models.TextChoices):
    """What happens to a challenge when resolved."""

    DESTROY = "destroy", "Destroy (removed for everyone)"
    PERSONAL = "personal", "Personal (resolved for this character only)"
    TEMPORARY = "temporary", "Temporary (suppressed for N rounds)"


class DifficultyIndicator(models.TextChoices):
    """Difficulty level shown to the player for an available action."""

    IMPOSSIBLE = "impossible", "Impossible"
    EASY = "easy", "Easy"
    MODERATE = "moderate", "Moderate"
    HARD = "hard", "Hard"
    VERY_HARD = "very_hard", "Very Hard"


class CapabilitySourceType(models.TextChoices):
    """Where a character's capability comes from."""

    TECHNIQUE = "technique", "Technique"
    TRAIT = "trait", "Trait"
    CONDITION = "condition", "Condition"
    EQUIPMENT = "equipment", "Equipment"


class EngagementType(models.TextChoices):
    """What kind of stakes-bearing activity a character is engaged in."""

    CHALLENGE = "challenge", "Challenge"
    COMBAT = "combat", "Combat"
    MISSION = "mission", "Mission"


class PropertyHolder(models.TextChoices):
    """Which entity holds the property being checked by a Prerequisite."""

    SELF = "self", "Character (self)"
    TARGET = "target", "Target object"
    LOCATION = "location", "Location (room)"


# Identifies which ModifierCategory values can receive equipment-driven contributions.
# get_modifier_total walks equipment only when target.category is in this set.
EQUIPMENT_RELEVANT_CATEGORIES: frozenset[str] = frozenset(
    {
        "stat",
        "magic",
        "affinity",
        "resonance",
        # #4333: favor targets take covenant role, covenant level and vow bonuses.
        # For these two the walk counts a covenant role once (see
        # world.mechanics.services.equipment_walk_total).
        "favor_invocation",
        "favor_earning",
        # Add more as PR3 lands combat stats and ItemCapabilityGrants.
    }
)
