"""Constants for the relationships app."""

from django.db import models


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
