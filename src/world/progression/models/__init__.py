"""
Progression models package.

This package organizes progression models into logical modules:
- rewards: XP and development point models
- unlocks: Unlock types, requirements, and XP cost system
"""

# Import all models from submodules for convenience
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
    # Requirements
    "AbstractClassLevelRequirement",
    "AchievementRequirement",
    # Character Unlocks
    "CharacterUnlock",
    "ClassLevelRequirement",
    # Unlock Types
    "ClassLevelUnlock",
    "ClassXPCost",
    "DevelopmentPoints",
    "DevelopmentTransaction",
    # Rewards
    "ExperiencePointsData",
    "LevelRequirement",
    "MultiClassLevel",
    "MultiClassRequirement",
    "RelationshipRequirement",
    "TierRequirement",
    "TraitRatingUnlock",
    "TraitRequirement",
    "TraitXPCost",
    # XP Cost System
    "XPCostChart",
    "XPCostEntry",
    "XPTransaction",
]
