"""Constants for the relationships app."""

from django.db import models

# Number of days for temporary points to fully decay (linear: 10%/day)
DECAY_DAYS = 10

# Maximum development updates per character per week (across all relationships)
MAX_DEVELOPMENTS_PER_WEEK = 7

# Points applied per ambient relationship bump — rel plus/neg, valenced emoji reactions (#1699).
BUMP_POINTS = 1


class TrackSystemKey(models.TextChoices):
    """Lookup keys for the generic system tracks that ambient bumps write to (#1699)."""

    REGARD = "regard", "Regard"
    FRICTION = "friction", "Friction"


class BumpValence(models.IntegerChoices):
    """Direction of an ambient relationship bump (#1699)."""

    POSITIVE = 1, "Positive"
    NEGATIVE = -1, "Negative"


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


# Per-commendation kudos award (staff-tunable; see KudosSourceCategory "relationship_writeup").
WRITEUP_KUDOS_AMOUNT: int = 1
# Natural key of the KudosSourceCategory row that explains writeup-commendation awards.
RELATIONSHIP_WRITEUP_KUDOS_CATEGORY: str = "relationship_writeup"


class ReferenceMode(models.TextChoices):
    """How a relationship update references RP."""

    ALL_WEEKLY = "all_weekly", "All Interactions This Week"
    SPECIFIC_INTERACTION = "specific_interaction", "Specific Interaction"
    SPECIFIC_SCENE = "specific_scene", "Specific Scene"
