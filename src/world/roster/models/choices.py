"""
Choices and validation constants for the roster system.
"""

from django.db import models


class ApplicationStatus(models.TextChoices):
    """Application status choices"""

    PENDING = "pending", "Pending Review"
    APPROVED = "approved", "Approved"
    DENIED = "denied", "Denied"
    WITHDRAWN = "withdrawn", "Withdrawn"


class PlotInvolvement(models.TextChoices):
    """Plot involvement level choices"""

    HIGH = "high", "High - Very Active"
    MEDIUM = "medium", "Medium - Moderate"
    LOW = "low", "Low - Minimal"
    NONE = "none", "None - Social Only"


class RosterType(models.TextChoices):
    """Common roster type names for validation"""

    ACTIVE = "Active", "Active"
    INACTIVE = "Inactive", "Inactive"
    AVAILABLE = "Available", "Available"
    RESTRICTED = "Restricted", "Restricted"  # Characters requiring special approval
    FROZEN = "Frozen", "Frozen"


class ActivityRequirement(models.TextChoices):
    """Per-Roster activity bar for inactivity-detection (#671).

    Drives the weekly sweep in world/roster/services/activity.py:
    HIGH-tier rosters key on Account.last_login PLUS RosterEntry.last_puppeted
    (any-persona IC action). LOW-tier rosters key on Account.last_login only.
    NONE-tier rosters never auto-mark characters INACTIVE.
    """

    HIGH = "HIGH", "High (any-persona IC action required)"
    LOW = "LOW", "Low (account login sufficient)"
    NONE = "NONE", "None (never auto-marked inactive)"


class ApprovalScope(models.TextChoices):
    """Approval scope choices for staff permissions"""

    ALL = "all", "All Characters"
    HOUSE = "house", "House Characters Only"
    STORY = "story", "Story Characters Only"
    NONE = "none", "No Approval Rights"


class ApplicationAction(models.TextChoices):
    """Actions that can be taken on an application"""

    APPROVE = "approve", "Approve"
    DENY = "deny", "Deny"


class ValidationErrorCodes:
    """Error codes for validation failures - for use with DRF serializers"""

    # Basic validation errors
    CHARACTER_NOT_ON_ROSTER = "character_not_on_roster"
    ALREADY_PLAYING_CHARACTER = "already_playing_character"
    CHARACTER_ALREADY_PLAYED = "character_already_played"
    DUPLICATE_PENDING_APPLICATION = "duplicate_pending_application"

    # Policy validation errors
    RESTRICTED_REQUIRES_REVIEW = "restricted_requires_review"
    INACTIVE_ROSTER = "inactive_roster"
    INSUFFICIENT_TRUST_LEVEL = "insufficient_trust_level"
    STORY_CONFLICT = "story_conflict"
    ROSTER_PERMISSION_DENIED = "roster_permission_denied"
    APPLICATION_LIMIT_EXCEEDED = "application_limit_exceeded"


class ValidationMessages:
    """User-friendly validation messages - for use with DRF serializers"""

    # Basic validation messages
    CHARACTER_NOT_ON_ROSTER = "Character is not on the roster"
    ALREADY_PLAYING_CHARACTER = "You are already playing this character"
    CHARACTER_ALREADY_PLAYED = "Character is already being played"
    DUPLICATE_PENDING_APPLICATION = "You already have a pending application for this character"

    # Policy validation messages
    RESTRICTED_REQUIRES_REVIEW = "Character requires special approval and trust evaluation"
    INACTIVE_ROSTER = "Character is in an inactive roster"
    INSUFFICIENT_TRUST_LEVEL = "Character requires higher trust level"
    STORY_CONFLICT = "Player involved in conflicting storylines"
    ROSTER_PERMISSION_DENIED = "Player not allowed to apply to this roster type"
    APPLICATION_LIMIT_EXCEEDED = "Too many pending applications"
