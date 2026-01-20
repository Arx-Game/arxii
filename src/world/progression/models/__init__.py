"""
Progression models package.

This package organizes progression models into logical modules:
- rewards: XP and development point models
- kudos: Kudos "good sport" currency models
- unlocks: Unlock types, requirements, and XP cost system
- paths: Character path history tracking
"""

# Import all models from submodules for convenience
from world.progression.models.kudos import (
    KudosClaimCategory,
    KudosPointsData,
    KudosSourceCategory,
    KudosTransaction,
)
from world.progression.models.paths import CharacterPathHistory
from world.progression.models.rewards import (
    DevelopmentPoints,
    DevelopmentTransaction,
    ExperiencePointsData,
    XPTransaction,
)
from world.progression.models.unlocks import (
    AbstractClassLevelRequirement,
    AchievementRequirement,
    CharacterUnlock,
    ClassLevelRequirement,
    ClassLevelUnlock,
    ClassXPCost,
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

# For backwards compatibility, make all models available at package level
__all__ = [
    "AbstractClassLevelRequirement",
    "AchievementRequirement",
    "CharacterPathHistory",
    "CharacterUnlock",
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
    "LevelRequirement",
    "MultiClassLevel",
    "MultiClassRequirement",
    "RelationshipRequirement",
    "TierRequirement",
    "TraitRatingUnlock",
    "TraitRequirement",
    "TraitXPCost",
    "XPCostChart",
    "XPCostEntry",
    "XPTransaction",
]
