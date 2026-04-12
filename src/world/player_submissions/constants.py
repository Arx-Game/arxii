"""Constants for player submission models."""

from django.db import models


class SubmissionStatus(models.TextChoices):
    """Status for player submissions."""

    OPEN = "open", "Open"
    REVIEWED = "reviewed", "Reviewed"
    DISMISSED = "dismissed", "Dismissed"


class SubmissionCategory(models.TextChoices):
    """Categories for the staff inbox aggregator.

    Each category corresponds to a different source model. Used by the
    staff inbox to filter and display items from distinct submission types.
    """

    PLAYER_FEEDBACK = "player_feedback", "Player Feedback"
    BUG_REPORT = "bug_report", "Bug Report"
    PLAYER_REPORT = "player_report", "Player Report"
    CHARACTER_APPLICATION = "character_application", "Character Application"
    GM_APPLICATION = "gm_application", "GM Application"
