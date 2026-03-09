"""Constants for the relationships app."""

from django.db import models

# Number of days for temporary points to fully decay (linear: 10%/day)
DECAY_DAYS = 10


class TrackSign(models.TextChoices):
    """Whether a relationship track represents positive or negative feelings."""

    POSITIVE = "positive", "Positive"
    NEGATIVE = "negative", "Negative"


class UpdateVisibility(models.TextChoices):
    """Who can see a relationship update or change."""

    PRIVATE = "private", "Private"
    SHARED = "shared", "Shared"
    GOSSIP = "gossip", "Gossip"
    PUBLIC = "public", "Public"


class FirstImpressionColoring(models.TextChoices):
    """The emotional coloring of a first impression."""

    POSITIVE = "positive", "Positive"
    NEUTRAL = "neutral", "Neutral"
    NEGATIVE = "negative", "Negative"
