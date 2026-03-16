"""Constants for the mechanics system."""

from django.db import models

# ModifierCategory name constants (must match fixture data)
STAT_CATEGORY_NAME = "stat"
GOAL_CATEGORY_NAME = "goal"
GOAL_PERCENT_CATEGORY_NAME = "goal_percent"
GOAL_POINTS_CATEGORY_NAME = "goal_points"
RESONANCE_CATEGORY_NAME = "resonance"


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
