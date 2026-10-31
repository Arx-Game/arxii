"""Constants for the mechanics system."""

from django.db import models

# Re-export from checks app for backwards compatibility
from world.checks.constants import EffectTarget, EffectType  # noqa: F401

# ModifierCategory name constants (must match fixture data)
STAT_CATEGORY_NAME = "stat"
#: One target per ``Aspect`` row (#4827): a distinction's +N on an Aspect is a modifier on
#: every check that weights it, scaled by the check's aspect weight.
ASPECT_CATEGORY_NAME = "aspect"
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
    # The sheet's CharacterModifier rows aimed at the capability's ModifierTarget
    # (species gifts, distinctions, worn gear), summed into one source (#4663).
    MODIFIER = "modifier", "Modifier"


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
        # #4783: listing this lets the equipment walk reach a maneuver-effect target:
        # the vow stat scaling part and the crossing-choice conditions of worn facets and
        # mantles. Distinctions, crafted recipe modifiers and active conditions reach it
        # without this entry. A facet's own tier-0 FLAT_BONUS pull does not (it needs a
        # resonance on the target). This set matches categories by name, the existing
        # practice for it, accepted knowingly here.
        "maneuver_effect",
        # Add more as PR3 lands combat stats and ItemCapabilityGrants.
    }
)


# ---------------------------------------------------------------------------
# Maneuver effects (#4783)
# ---------------------------------------------------------------------------

# The ModifierCategory a maneuver-effect target lives in. Created by migration 0334, and
# in code by name (``ensure_maneuver_effects``) for a schema built without migrations.
MANEUVER_EFFECT_CATEGORY_NAME = "maneuver_effect"


class ManeuverEffectKey(models.TextChoices):
    """One named part of a combat maneuver, each with one number (#4783)."""

    CHARGE_TO_HIT = "charge_to_hit", "Charge: to hit"
    CHARGE_DAMAGE = "charge_damage", "Charge: damage"
    CHARGE_REACH = "charge_reach", "Charge: reach"
    COVER_ESCAPE_BONUS = "cover_escape_bonus", "Cover: escape bonus"
    SUCCOR_PARTIAL_PROTECTION = (
        "succor_partial_protection",
        "Succor: partial protection",
    )
    INTERPOSE_PARTIAL_PROTECTION = (
        "interpose_partial_protection",
        "Interpose: partial protection",
    )
    RALLY_MORALE = "rally_morale", "Rally: morale"
    RALLY_SURGE_INTENSITY = "rally_surge_intensity", "Rally: surge intensity"


class EffectKind(models.TextChoices):
    """What sort of number a maneuver effect is; a broad target names a kind (#4783).

    Each kind fixes the unit of every modifier that targets it.
    """

    TO_HIT = "to_hit", "To hit"
    DAMAGE = "damage", "Damage"
    REACH = "reach", "Reach"
    ESCAPE_BONUS = "escape_bonus", "Escape bonus"
    PARTIAL_PROTECTION = "partial_protection", "Partial protection"
    MORALE = "morale", "Morale"
    SURGE_INTENSITY = "surge_intensity", "Surge intensity"
    CONDITION_SEVERITY = "condition_severity", "Condition severity"
    CONDITION_DURATION = "condition_duration", "Condition duration"


# The kinds a technique scope can narrow: the ones a technique's cast reads (#4822).
TECHNIQUE_SCOPE_KINDS: tuple[str, ...] = (
    EffectKind.DAMAGE,
    EffectKind.CONDITION_SEVERITY,
    EffectKind.CONDITION_DURATION,
)

MANEUVER_EFFECT_KIND: dict[str, str] = {
    ManeuverEffectKey.CHARGE_TO_HIT: EffectKind.TO_HIT,
    ManeuverEffectKey.CHARGE_DAMAGE: EffectKind.DAMAGE,
    ManeuverEffectKey.CHARGE_REACH: EffectKind.REACH,
    ManeuverEffectKey.COVER_ESCAPE_BONUS: EffectKind.ESCAPE_BONUS,
    ManeuverEffectKey.SUCCOR_PARTIAL_PROTECTION: EffectKind.PARTIAL_PROTECTION,
    ManeuverEffectKey.INTERPOSE_PARTIAL_PROTECTION: EffectKind.PARTIAL_PROTECTION,
    ManeuverEffectKey.RALLY_MORALE: EffectKind.MORALE,
    ManeuverEffectKey.RALLY_SURGE_INTENSITY: EffectKind.SURGE_INTENSITY,
}

# Today's number for each effect: what a maneuver gives with no modifier anywhere.
# Charge hops, Cover per coverer, partial protection and surge intensity are
# percentages or counts as their kind says; morale is per success level.
MANEUVER_EFFECT_DEFAULTS: dict[str, int] = {
    ManeuverEffectKey.CHARGE_TO_HIT: 10,
    ManeuverEffectKey.CHARGE_DAMAGE: 5,
    ManeuverEffectKey.CHARGE_REACH: 5,
    ManeuverEffectKey.COVER_ESCAPE_BONUS: 10,
    ManeuverEffectKey.SUCCOR_PARTIAL_PROTECTION: 50,
    ManeuverEffectKey.INTERPOSE_PARTIAL_PROTECTION: 50,
    ManeuverEffectKey.RALLY_MORALE: 15,
    ManeuverEffectKey.RALLY_SURGE_INTENSITY: 100,
}
