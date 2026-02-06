"""Character creation constants.

TextChoices and IntegerChoices are placed here to avoid circular imports
and keep models.py focused on model definitions.
"""

from django.db import models


class Stage(models.IntegerChoices):
    """Character creation stages."""

    ORIGIN = 1, "Origin"
    HERITAGE = 2, "Heritage"
    LINEAGE = 3, "Lineage"
    DISTINCTIONS = 4, "Distinctions"
    PATH_SKILLS = 5, "Path & Skills"
    ATTRIBUTES = 6, "Attributes"
    MAGIC = 7, "Magic"
    APPEARANCE = 8, "Appearance"
    IDENTITY = 9, "Identity"
    FINAL_TOUCHES = 10, "Final Touches"
    REVIEW = 11, "Review"


class StartingAreaAccessLevel(models.TextChoices):
    """Access levels for starting areas in character creation."""

    ALL = "all", "All Players"
    TRUST_REQUIRED = "trust_required", "Trust Required"
    STAFF_ONLY = "staff_only", "Staff Only"
