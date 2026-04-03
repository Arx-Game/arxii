"""
Constants for the progression system.
"""

from django.db import models


class VoteTargetType(models.TextChoices):
    """Types of content that can receive weekly votes."""

    INTERACTION = "interaction", "Interaction"
    SCENE_PARTICIPATION = "scene_participation", "Scene Participation"
    JOURNAL = "journal", "Journal Entry"


# Vote budget
DEFAULT_BASE_VOTES = 7
MAX_SCENE_BONUS_VOTES = 7

# XP award amounts
MEMORABLE_POSE_XP = [3, 2, 1]  # 1st, 2nd, 3rd place
VOTE_XP_CAP = 50

# Random scene XP
RS_BASE_XP = 5
RS_FIRST_TIME_BONUS = 10
RS_PARTNER_XP = 5

# First impression XP
FIRST_IMPRESSION_AUTHOR_XP = 3
FIRST_IMPRESSION_TARGET_XP = 5

# Development point level-up formula constants
# Cost from level N to N+1 = (N - DP_COST_OFFSET) * DP_COST_MULTIPLIER
DP_BASE_LEVEL = 10  # CG starting level; no dp needed at or below this level
DP_COST_OFFSET = 9  # Subtracted from level in cost formula
DP_COST_MULTIPLIER = 100  # Multiplied by (level - offset) for per-level cost

# Skill rust constants
RUST_BASE_AMOUNT = 5  # Added to character_level for weekly rust
