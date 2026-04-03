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
    VOTE_REWARD = "vote_reward", "Vote Reward"
    MEMORABLE_POSE = "memorable_pose", "Memorable Pose"
    RANDOM_SCENE = "random_scene", "Random Scene"
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
    "SELF_VOTE": "Cannot vote for your own content.",
    "NO_VOTES_REMAINING": "No votes remaining this week.",
    "ALREADY_VOTED": "Already voted for this content this week.",
    "VOTE_NOT_FOUND": "Vote not found for this content this week.",
    "VOTE_PROCESSED": "Cannot remove a processed vote.",
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

    SELF_VOTE = _PROGRESSION_ERROR_MESSAGES["SELF_VOTE"]
    NO_VOTES_REMAINING = _PROGRESSION_ERROR_MESSAGES["NO_VOTES_REMAINING"]
    ALREADY_VOTED = _PROGRESSION_ERROR_MESSAGES["ALREADY_VOTED"]
    VOTE_NOT_FOUND = _PROGRESSION_ERROR_MESSAGES["VOTE_NOT_FOUND"]
    VOTE_PROCESSED = _PROGRESSION_ERROR_MESSAGES["VOTE_PROCESSED"]
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
