"""
Type definitions for the progression system.
"""

from django.db import models


class UnlockType(models.TextChoices):
    """Types of unlocks that can be purchased with XP."""

    LEVEL = "level", "Level Increase"
    SKILL_RATING = "skill_rating", "Skill Rating"
    STAT_RATING = "stat_rating", "Stat Rating"
    ABILITY = "ability", "Special Ability"
    OTHER = "other", "Other"


class DevelopmentSource(models.TextChoices):
    """Sources that can award development points."""

    SCENE = "scene", "Scene Participation"
    TRAINING = "training", "Training Activity"
    PRACTICE = "practice", "Practice Session"
    TEACHING = "teaching", "Teaching Others"
    QUEST = "quest", "Quest Completion"
    EXPLORATION = "exploration", "Exploration"
    CRAFTING = "crafting", "Crafting Activity"
    COMBAT = "combat", "Combat Encounter"
    SOCIAL = "social", "Social Activity"
    OTHER = "other", "Other Activity"


class ProgressionReason(models.TextChoices):
    """Reasons for progression changes."""

    XP_PURCHASE = "xp_purchase", "XP Purchase"
    SCENE_AWARD = "scene_award", "Scene Award"
    GM_AWARD = "gm_award", "GM Award"
    SYSTEM_AWARD = "system_award", "System Award"
    REFUND = "refund", "Refund"
    CORRECTION = "correction", "GM Correction"
    OTHER = "other", "Other"
