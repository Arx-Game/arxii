"""
Type definitions for the progression system.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypedDict

from django.db import models

if TYPE_CHECKING:
    from world.progression.models import KudosPointsData, KudosTransaction


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
    CG_CONVERSION = "cg_conversion", "CG Point Conversion"
    SCENE_AWARD = "scene_award", "Scene Award"
    GM_AWARD = "gm_award", "GM Award"
    SYSTEM_AWARD = "system_award", "System Award"
    REFUND = "refund", "Refund"
    CORRECTION = "correction", "GM Correction"
    KUDOS_CLAIM = "kudos_claim", "Kudos Claim"
    OTHER = "other", "Other"


@dataclass
class AwardResult:
    """Result of awarding kudos to an account."""

    points_data: "KudosPointsData"
    transaction: "KudosTransaction"


@dataclass
class ClaimResult:
    """Result of claiming kudos from an account."""

    points_data: "KudosPointsData"
    transaction: "KudosTransaction"
    reward_amount: int


class UnlockEntry(TypedDict):
    unlock: object  # ClassLevelUnlock
    type: str


class DetailedUnlockEntry(TypedDict):
    unlock: object  # ClassLevelUnlock
    type: str
    xp_cost: int
    requirements_met: bool
    failed_requirements: list[str]


class AvailableUnlocks(TypedDict):
    available: list[DetailedUnlockEntry]
    locked: list[DetailedUnlockEntry]
    already_unlocked: list[UnlockEntry]


class LevelUpRequirements(TypedDict):
    character_class: str
    current_level: int
    target_level: int
    xp_cost: int
    requirements_met: bool
    failed_requirements: list[str]
    unlock: object  # ClassLevelUnlock
