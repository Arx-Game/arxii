"""
Progression models package.

This package organizes progression models into logical modules:
- advancement: Class-level advancement receipts and shared abstract base
- rewards: XP and development point models
- kudos: Kudos "good sport" currency models
- unlocks: Unlock types, requirements, and XP cost system
- paths: Character path history tracking
- voting: Weekly vote budget and vote tracking
- random_scene: Weekly random scene targets and completion tracking
- engagement: Weekly social-engagement pending ledger
"""

# Import all models from submodules for convenience
from world.progression.models.advancement import (
    AbstractClassLevelAdvancement,
    ClassLevelAdvancement,
    DuranceTrainingSite,
)
from world.progression.models.character_xp import (
    CharacterXP,
    CharacterXPTransaction,
)
from world.progression.models.engagement import (
    WeeklyEngagementInitiator,
    WeeklySocialEngagement,
)
from world.progression.models.kudos import (
    KudosClaimCategory,
    KudosDifficultyWeight,
    KudosPointsData,
    KudosSourceCategory,
    KudosTransaction,
)
from world.progression.models.path_intent import PathIntent
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
    AbstractUnlockRequirement,
    AchievementRequirement,
    CharacterUnlock,
    ClassLevelRequirement,
    ClassLevelUnlock,
    ClassXPCost,
    CodexKnowledgeRequirement,
    ItemRequirement,
    LegendRequirement,
    LevelRequirement,
    MajorGiftTechniqueRequirement,
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
    "AbstractClassLevelAdvancement",
    "AbstractClassLevelRequirement",
    "AbstractUnlockRequirement",
    "AchievementRequirement",
    "CharacterPathHistory",
    "CharacterUnlock",
    "CharacterXP",
    "CharacterXPTransaction",
    "ClassLevelAdvancement",
    "ClassLevelRequirement",
    "ClassLevelUnlock",
    "ClassXPCost",
    "CodexKnowledgeRequirement",
    "DevelopmentPoints",
    "DevelopmentTransaction",
    "DuranceTrainingSite",
    "ExperiencePointsData",
    "ItemRequirement",
    "KudosClaimCategory",
    "KudosDifficultyWeight",
    "KudosPointsData",
    "KudosSourceCategory",
    "KudosTransaction",
    "LegendRequirement",
    "LevelRequirement",
    "MajorGiftTechniqueRequirement",
    "MultiClassLevel",
    "MultiClassRequirement",
    "PathIntent",
    "RandomSceneCompletion",
    "RandomSceneTarget",
    "RelationshipRequirement",
    "TierRequirement",
    "TraitRatingUnlock",
    "TraitRequirement",
    "TraitXPCost",
    "WeeklyEngagementInitiator",
    "WeeklySkillUsage",
    "WeeklySocialEngagement",
    "WeeklyVote",
    "WeeklyVoteBudget",
    "XPCostChart",
    "XPCostEntry",
    "XPTransaction",
    "cumulative_dp_for_level",
]
