"""Character creation constants.

TextChoices and IntegerChoices are placed here to avoid circular imports
and keep models.py focused on model definitions.
"""

from django.db import models

from world.traits.constants import PrimaryStat

# Primary stat constants (simplified 1-5 scale, no divisor)
STAT_MIN_VALUE = 1  # Minimum stat value
STAT_MAX_VALUE = 5  # Maximum stat value during character creation
STAT_DEFAULT_VALUE = 2  # Default starting value

# Legacy constants - kept until models.py/validators.py/serializers.py are updated in Task 2
STAT_DISPLAY_DIVISOR = 10
STAT_FREE_POINTS = 5
STAT_BASE_POINTS = 18
STAT_TOTAL_BUDGET = STAT_BASE_POINTS + STAT_FREE_POINTS

# Age constraints for character creation
AGE_MIN = 18
AGE_MAX = 65

# Required primary stat names
REQUIRED_STATS = PrimaryStat.get_all_stat_names()


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


class ApplicationStatus(models.TextChoices):
    """Status choices for draft applications."""

    SUBMITTED = "submitted", "Submitted"
    IN_REVIEW = "in_review", "In Review"
    REVISIONS_REQUESTED = "revisions_requested", "Revisions Requested"
    APPROVED = "approved", "Approved"
    DENIED = "denied", "Denied"
    WITHDRAWN = "withdrawn", "Withdrawn"


class CommentType(models.TextChoices):
    """Types of application comments."""

    MESSAGE = "message", "Message"
    STATUS_CHANGE = "status_change", "Status Change"
