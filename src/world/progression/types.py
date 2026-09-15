"""
Type definitions for the progression system.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypedDict

from django.db import models

if TYPE_CHECKING:
    from world.progression.models import (
        ClassLevelUnlock,
        KudosPointsData,
        KudosTransaction,
        XPTransaction,
    )


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
    RUST = "rust", "Skill Rust"
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
    FIRST_IMPRESSION = "first_impression", "First Impression"
    # Reason keys stay within the 20-character reason column.
    NOMINATION = "nomination", "Nominations"
    MOST_NOMINATED_PROSE = "top_prose", "Most Nominated Prose"
    BEST_IN_SCENE = "best_in_scene", "Best in Scene"
    MOST_NOMINATED_JOURNAL = "top_journal", "Most Nominated Journal"
    RANDOM_SCENE = "random_scene", "Random Scene"
    GM_STORY_REWARD = "gm_story_reward", "GM Story Reward"
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


@dataclass
class KudosXPResult:
    """Result of claiming kudos and converting to XP."""

    claim_result: ClaimResult
    xp_transaction: "XPTransaction"
    xp_awarded: int


class UnlockEntry(TypedDict):
    unlock: "ClassLevelUnlock"
    type: str


class DetailedUnlockEntry(TypedDict):
    unlock: "ClassLevelUnlock"
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
    unlock: "ClassLevelUnlock"


_PROGRESSION_ERROR_MESSAGES: dict[str, str] = {
    "SELF_NOMINATION": "You cannot nominate your own characters.",
    "ALREADY_NOMINATED": "You already nominated this piece this week.",
    "NOMINATION_NOT_FOUND": "No nomination of yours on this piece this week.",
    "NOMINATION_PROCESSED": "That week has settled; the nomination stands.",
    "NOT_THIS_WEEK": "Only prose from this week can be nominated.",
    "NOT_VISIBLE": "You can only nominate what you have seen.",
    "NO_PLAYER": "Nobody is playing that character to receive it.",
    "NO_AUTHOR": "Could not determine the author of this content.",
    "RS_NOT_FOUND": "Random scene target not found for this slot.",
    "RS_ALREADY_CLAIMED": "This random scene target is already claimed.",
    "RS_NO_EVIDENCE": "No shared RP evidence found for this claim.",
    "RS_ALREADY_REROLLED": "Already used reroll this week.",
    "RS_CLAIMED_REROLL": "Cannot reroll a claimed target.",
    "RS_NO_CANDIDATES": "No available characters to reroll to.",
}


class ProgressionError(Exception):
    """User-safe error from progression operations.

    Always raised with one of the class-level message constants. Use
    ``exc.user_message`` in API responses instead of ``str(exc)`` to
    avoid CodeQL "information exposure through exception" warnings.
    """

    SELF_NOMINATION = _PROGRESSION_ERROR_MESSAGES["SELF_NOMINATION"]
    ALREADY_NOMINATED = _PROGRESSION_ERROR_MESSAGES["ALREADY_NOMINATED"]
    NOMINATION_NOT_FOUND = _PROGRESSION_ERROR_MESSAGES["NOMINATION_NOT_FOUND"]
    NOMINATION_PROCESSED = _PROGRESSION_ERROR_MESSAGES["NOMINATION_PROCESSED"]
    NOT_THIS_WEEK = _PROGRESSION_ERROR_MESSAGES["NOT_THIS_WEEK"]
    NOT_VISIBLE = _PROGRESSION_ERROR_MESSAGES["NOT_VISIBLE"]
    NO_PLAYER = _PROGRESSION_ERROR_MESSAGES["NO_PLAYER"]
    NO_AUTHOR = _PROGRESSION_ERROR_MESSAGES["NO_AUTHOR"]
    RS_NOT_FOUND = _PROGRESSION_ERROR_MESSAGES["RS_NOT_FOUND"]
    RS_ALREADY_CLAIMED = _PROGRESSION_ERROR_MESSAGES["RS_ALREADY_CLAIMED"]
    RS_NO_EVIDENCE = _PROGRESSION_ERROR_MESSAGES["RS_NO_EVIDENCE"]
    RS_ALREADY_REROLLED = _PROGRESSION_ERROR_MESSAGES["RS_ALREADY_REROLLED"]
    RS_CLAIMED_REROLL = _PROGRESSION_ERROR_MESSAGES["RS_CLAIMED_REROLL"]
    RS_NO_CANDIDATES = _PROGRESSION_ERROR_MESSAGES["RS_NO_CANDIDATES"]

    @property
    def user_message(self) -> str:
        msg = self.args[0] if self.args else ""
        if msg in _PROGRESSION_ERROR_MESSAGES.values():
            return msg
        return "An unexpected progression error occurred."
