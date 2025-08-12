"""
Progression models package.

This package organizes progression models into logical modules:
- rewards: XP and development point models
- unlocks: Unlock types, requirements, and XP cost system
"""

# Import all models from submodules for convenience
from world.progression.models.rewards import (  # noqa: I252
    DevelopmentPoints,
    DevelopmentTransaction,
    ExperiencePointsData,
    XPTransaction,
)
from world.progression.models.unlocks import (  # noqa: I252
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
    # Rewards
    "ExperiencePointsData",
    "XPTransaction",
    "DevelopmentPoints",
    "DevelopmentTransaction",
    # XP Cost System
    "XPCostChart",
    "XPCostEntry",
    "ClassXPCost",
    "TraitXPCost",
    # Unlock Types
    "ClassLevelUnlock",
    "TraitRatingUnlock",
    # Requirements
    "AbstractClassLevelRequirement",
    "TraitRequirement",
    "LevelRequirement",
    "ClassLevelRequirement",
    "MultiClassRequirement",
    "MultiClassLevel",
    "AchievementRequirement",
    "RelationshipRequirement",
    "TierRequirement",
    # Character Unlocks
    "CharacterUnlock",
]
