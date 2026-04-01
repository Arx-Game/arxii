"""
Constants for the progression system.
"""

from django.db import models


class VoteTargetType(models.TextChoices):
    """Types of content that can receive weekly votes."""

    INTERACTION = "interaction", "Interaction"
    SCENE_PARTICIPATION = "scene_participation", "Scene Participation"
    JOURNAL = "journal", "Journal Entry"
