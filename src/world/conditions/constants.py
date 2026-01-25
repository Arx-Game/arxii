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
    PERMANENT = "permanent", "Permanent (until removed)"


class StackBehavior(models.TextChoices):
    """What stacking affects for stackable conditions."""

    INTENSITY = "intensity", "Stacks increase intensity/severity"
    DURATION = "duration", "Stacks increase duration"
    BOTH = "both", "Stacks increase both"


class CapabilityEffectType(models.TextChoices):
    """Effect types for condition capability effects."""

    BLOCKED = "blocked", "Blocked (cannot use)"
    REDUCED = "reduced", "Reduced (percentage penalty)"
    ENHANCED = "enhanced", "Enhanced (percentage bonus)"


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
