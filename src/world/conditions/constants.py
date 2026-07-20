"""
Constants and enums for the conditions system.

TextChoices are defined here rather than in models.py to avoid circular
import issues when serializers need to reference them.
"""

from django.db import models


class DurationType(models.TextChoices):
    """Duration types for conditions."""

    ROUNDS = "rounds", "Rounds"
    UNTIL_CURED = "until_cured", "Until Cured"
    UNTIL_USED = "until_used", "Until Used (consumed on trigger)"
    UNTIL_END_OF_COMBAT = "end_combat", "Until End of Combat"
    SCENE = "scene", "Until End of Scene"
    INGAME_TIME = "ingame_time", "In-Game Time (expires after IC duration)"
    PERMANENT = "permanent", "Permanent (until removed)"


class StackBehavior(models.TextChoices):
    """What stacking affects for stackable conditions."""

    INTENSITY = "intensity", "Stacks increase intensity/severity"
    DURATION = "duration", "Stacks increase duration"
    BOTH = "both", "Stacks increase both"


class DamageTickTiming(models.TextChoices):
    """When damage-over-time effects tick."""

    START_OF_ROUND = "start", "Start of Round"
    END_OF_ROUND = "end", "End of Round"
    ON_ACTION = "action", "When Target Takes Action"


class ConditionInteractionTrigger(models.TextChoices):
    """Triggers for condition-condition interactions."""

    ON_OTHER_APPLIED = "on_other_applied", "When other condition is applied"
    ON_SELF_APPLIED = "on_self_applied", "When this condition is applied"
    WHILE_BOTH_PRESENT = "while_both", "While both are present"


class ConditionInteractionOutcome(models.TextChoices):
    """Outcomes for condition-condition interactions."""

    REMOVE_SELF = "remove_self", "Remove this condition"
    REMOVE_OTHER = "remove_other", "Remove other condition"
    REMOVE_BOTH = "remove_both", "Remove both conditions"
    PREVENT_OTHER = "prevent_other", "Prevent other from being applied"
    PREVENT_SELF = "prevent_self", "Prevent this from being applied"
    TRANSFORM_SELF = "transform_self", "Transform this into another condition"
    MERGE = "merge", "Merge into a different condition"


class TreatmentTargetKind(models.TextChoices):
    """What a TreatmentTemplate is authored to target."""

    PRIMARY = "primary", "Primary condition severity"
    AFTERMATH = "aftermath", "Aftermath child condition severity"
    PENDING_ALTERATION = "pending_alteration", "Pending alteration tier"


# Discriminator recorded on each candidate dict's ``target_effect_type`` key by
# get_treatment_candidates, distinguishing a ConditionInstance target from a
# PendingAlteration target. Plain strings (not TextChoices) — an internal
# discriminator, not a model field or enumerated selection set.
TARGET_EFFECT_CONDITION: str = "condition"
TARGET_EFFECT_ALTERATION: str = "alteration"


# Foundational capability name constants.
# These are plain string constants (not Django choices) because they are
# capability identifiers, not an enumerated selection set.
# Each has innate_baseline >= 1 on its CapabilityType row, meaning every
# character possesses them by default before any condition modifier is applied.
# Condition name constants for the core incapacitation conditions.
# These are plain strings (not TextChoices) — they are identity keys,
# not an enumerated selection set. Factories use them to seed the
# ConditionTemplate rows; services use them to locate active instances.
UNCONSCIOUS_CONDITION_NAME: str = "Unconscious"
BLEED_OUT_CONDITION_NAME: str = "Bleeding Out"
SURROUNDED_CONDITION_NAME: str = "Surrounded"  # #1733 battle acute peril, staged
FORCE_FIELD_CONDITION_NAME: str = "Aegis Field"  # absorb_pool reactive handler (#1584)
REFLECT_CONDITION_NAME: str = "Mirror Ward"  # reflect_damage reactive handler (#1584)
BLINK_CONDITION_NAME: str = "Phase Step"  # blink_dodge reactive handler (#1584)
SUMMONING_CONDITION_NAME: str = "Summoning"  # active CONDITION_APPLIED summon trigger (#1584)

# Task 14c simple effect bundles (#1584). These names locate the ConditionTemplate rows
# seeded by ensure_teleport_content / ensure_obstacle_content / ensure_incorporeal_content /
# ensure_sink_content / ensure_telekinesis_content in world.magic.effect_palette_content.
TELEPORT_CONDITION_NAME: str = "Phase Jump"  # CONDITION_APPLIED → move_position (SELF)
OBSTACLE_CONDITION_NAME: str = "Barricade"  # CONDITION_APPLIED → create_obstacle (SELF)
INCORPOREAL_CONDITION_NAME: str = "Ghostform"  # intangibility gate only; no handler
SINK_CONDITION_NAME: str = "Earthmeld"  # intangibility gate, 1-round duration; no handler
TELEKINESIS_CONDITION_NAME: str = "Force Grip"  # CONDITION_APPLIED → move_position (ENEMY)

# Poison content identity keys (#1050). The DamageType, the staged acute
# Poisoned ConditionTemplate, and the long-term Slow Poison variant are seeded
# idempotently by ensure_poison_content(); these names locate those rows.
POISON_DAMAGE_TYPE_NAME: str = "Poison"
POISONED_CONDITION_NAME: str = "Poisoned"
SLOW_POISON_CONDITION_NAME: str = "Slow Poison"
POISON_CATEGORY_NAME: str = "Poison"

# Charm/Calm content identity keys (#1590). Seeded idempotently by
# ensure_charm_content() in world.conditions.charm_content.
CHARM_CONDITION_NAME: str = "Charmed"
CALM_CONDITION_NAME: str = "Calm"


class Allegiance(models.TextChoices):
    """Behavioral allegiance states used by charm/control effects.

    Declared in the conditions constants module so combat and social code can
    share one source of truth.
    """

    ENEMY = "enemy", "Enemy"
    ALLY_OF_CASTER = "ally", "Fights for the charmer"
    NEUTRAL = "neutral", "Will not attack"


class FoundationalCapability:
    """String constants for capabilities every character has innately.

    The default value (baseline) each character has for these capabilities
    lives on CapabilityType.innate_baseline. Conditions that zero out these
    capabilities (e.g., unconscious zeroes AWARENESS, rooted zeroes MOVEMENT)
    use a sufficiently large negative ConditionCapabilityEffect.
    """

    AWARENESS = "awareness"  # required by ~all techniques; unconscious zeroes it
    MOVEMENT = "movement"  # locomotion; immobilized/rooted zeroes it
    LIMB_USE = "limb_use"  # using arms/hands; bound reduces it
