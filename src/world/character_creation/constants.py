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
    ATTRIBUTES = 4, "Attributes"
    PATH_SKILLS = 5, "Path & Skills"
    DISTINCTIONS = 6, "Distinctions"
    MAGIC = 7, "Magic"
    APPEARANCE = 8, "Appearance"
    IDENTITY = 9, "Identity"
    FINAL_TOUCHES = 10, "Final Touches"
    REVIEW = 11, "Review"
