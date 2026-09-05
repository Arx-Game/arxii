"""
Constants for the progression system.
"""

import types

from django.db import models

from world.fatigue.constants import EffortLevel


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

# Path level divisor for dp multiplier calculation
PATH_LEVEL_DIVISOR = 2  # dp multiplier = 1 + (path_level // PATH_LEVEL_DIVISOR)

# Base dp earned per qualifying check, keyed by EffortLevel enum values.
# Immutable to prevent accidental mutation of game constants.
EFFORT_DEV_BASE: types.MappingProxyType[str, int] = types.MappingProxyType(
    {
        EffortLevel.VERY_LOW: 0,
        EffortLevel.LOW: 0,
        EffortLevel.MEDIUM: 10,
        EffortLevel.HIGH: 20,
        EffortLevel.EXTREME: 30,
    }
)


# Maturation Points (#2756) — deterministic milestones for actually aging.
# PLACEHOLDER tuning: first milestone at matured-year 21, then every 3 years.
#: Maturation milestones (#2756, retuned #3635): the matured years at which a
#: Maturation Point is earned. The spacing widens with age and stops at 75; a
#: mortal past that is on borrowed time. Year 21 is deliberately not a milestone.
MATURATION_MILESTONES: tuple[int, ...] = (24, 27, 30, 34, 38, 42, 47, 52, 58, 64, 75)
#: A starting age below this costs one CG point at character creation (#3635):
#: the youngest characters buy their youth with a thinner purse.
MATURATION_UNDERAGE_YEAR = 21
UNDERAGE_CG_POINT_COST = 1
