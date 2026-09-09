"""
Constants for the progression system.
"""

import types

from django.db import models

from world.fatigue.constants import EffortLevel


class NominationTargetType(models.TextChoices):
    """The prose a nomination hangs off (#3738): a pose or a journal entry.

    A nomination is "I am voting this person for good RP because of this" — the
    piece only says where you read them; the nominee is the character who wrote it.
    """

    INTERACTION = "interaction", "Interaction"
    JOURNAL = "journal", "Journal Entry"


# Nomination settlement (#3738, the reviewer's curve, ruled 2026-09-09).
#
# Every settlement path counts something for the week and pays on one stepped
# curve: the count's tier is one XP step. The tier floors to 133 are the
# reviewer's exact numbers ("1 | 2 to 3 | 4 to 6 | 7 to 10 | 11 to 16 | 17 to 25
# | 26 to 38 | 39 to 58 | 59 to 88 | 89 to 133"); past the table each tier widens
# by half again (``stepped_xp`` in ``services.nomination_processing``). There is
# no other cap: the curve is the cap.
NOMINATION_TIER_FLOORS: tuple[int, ...] = (1, 2, 4, 7, 11, 17, 26, 39, 59, 89, 134)
# "Nominations in general" is front-loaded so one good scene with one close
# friend is not left in the dust: the first nominator is worth 3, each tier +1.
NOMINATION_FIRST_XP = 3
# "Best per scene" counts scene wins on the same curve from 1.
BEST_IN_SCENE_FIRST_XP = 1
# "Most nominated prose" is one instance per nominee per week by definition, so
# a flat 1; "most nominated journal" is one writer (or a tie) game-wide.
MOST_NOMINATED_PROSE_XP = 1
MOST_NOMINATED_JOURNAL_XP = 1

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
