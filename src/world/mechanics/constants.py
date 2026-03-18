"""Constants for the mechanics system."""

from django.db import models

# ModifierCategory name constants (must match fixture data)
STAT_CATEGORY_NAME = "stat"
GOAL_CATEGORY_NAME = "goal"
GOAL_PERCENT_CATEGORY_NAME = "goal_percent"
GOAL_POINTS_CATEGORY_NAME = "goal_points"
RESONANCE_CATEGORY_NAME = "resonance"

# ModifierSource.source_type return values
SOURCE_TYPE_DISTINCTION = "distinction"
SOURCE_TYPE_UNKNOWN = "unknown"


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


class EffectType(models.TextChoices):
    """Type of mechanical effect applied by a consequence."""

    APPLY_CONDITION = "apply_condition", "Apply Condition"
    REMOVE_CONDITION = "remove_condition", "Remove Condition"
    ADD_PROPERTY = "add_property", "Add Property"
    REMOVE_PROPERTY = "remove_property", "Remove Property"
    DEAL_DAMAGE = "deal_damage", "Deal Damage"
    LAUNCH_ATTACK = "launch_attack", "Launch Attack"
    LAUNCH_FLOW = "launch_flow", "Launch Flow"
    GRANT_CODEX = "grant_codex", "Grant Codex Entry"


class EffectTarget(models.TextChoices):
    """What the effect targets."""

    SELF = "self", "Self (acting character)"
    LOCATION = "location", "Location (challenge's room)"
