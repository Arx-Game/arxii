"""
Progression models package.

This package organizes progression models into logical modules:
- rewards: XP and development point models
- kudos: Kudos "good sport" currency models
- unlocks: Unlock types, requirements, and XP cost system
- paths: Character path history tracking
- voting: Weekly vote budget and vote tracking
- random_scene: Weekly random scene targets and completion tracking
"""

# Import all models from submodules for convenience
from world.progression.models.character_xp import (
    CharacterXP,
    CharacterXPTransaction,
)
from world.progression.models.kudos import (
    KudosClaimCategory,
    KudosPointsData,
    KudosSourceCategory,
    KudosTransaction,
)
from world.progression.models.paths import CharacterPathHistory
from world.progression.models.random_scene import (
    RandomSceneCompletion,
    RandomSceneTarget,
)
from world.progression.models.rewards import (
    DevelopmentPoints,
    DevelopmentTransaction,
    ExperiencePointsData,
    WeeklySkillUsage,
    XPTransaction,
    cumulative_dp_for_level,
)
from world.progression.models.unlocks import (
    AbstractClassLevelRequirement,
    AchievementRequirement,
    CharacterUnlock,
    ClassLevelRequirement,
    ClassLevelUnlock,
    ClassXPCost,
    LegendRequirement,
    LevelRequirement,
    MultiClassLevel,
    MultiClassRequirement,
    RelationshipRequirement,
    TierRequirement,
    TraitRatingUnlock,
    TraitRequirement,
    TraitXPCost,
    XPCostChart,
    XPCostEntry,
)
from world.progression.models.voting import (
    WeeklyVote,
    WeeklyVoteBudget,
)

# For backwards compatibility, make all models available at package level
__all__ = [
    "AbstractClassLevelRequirement",
    "AchievementRequirement",
    "CharacterPathHistory",
    "CharacterUnlock",
    "CharacterXP",
    "CharacterXPTransaction",
    "ClassLevelRequirement",
    "ClassLevelUnlock",
    "ClassXPCost",
    "DevelopmentPoints",
    "DevelopmentTransaction",
    "ExperiencePointsData",
    "KudosClaimCategory",
    "KudosPointsData",
    "KudosSourceCategory",
    "KudosTransaction",
    "LegendRequirement",
    "LevelRequirement",
    "MultiClassLevel",
    "MultiClassRequirement",
    "RandomSceneCompletion",
    "RandomSceneTarget",
    "RelationshipRequirement",
    "TierRequirement",
    "TraitRatingUnlock",
    "TraitRequirement",
    "TraitXPCost",
    "WeeklySkillUsage",
    "WeeklyVote",
    "WeeklyVoteBudget",
    "XPCostChart",
    "XPCostEntry",
    "XPTransaction",
    "cumulative_dp_for_level",
]
