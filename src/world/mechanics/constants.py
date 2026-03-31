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
TECHNIQUE_STAT_CATEGORY_NAME = "technique_stat"

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
