"""
Progression services package.

This package organizes progression services into logical modules:
- awards: Functions for awarding XP and development points
- cg_conversion: CG-to-XP conversion for character creation
- spends: Functions for spending XP on unlocks
- scene_integration: Scene-based reward integration
- kudos: Functions for awarding and claiming kudos
- scene_rewards: Scene completion rewards (vote budget bonuses)
"""

# Import key functions from submodules for convenience
from world.progression.services.awards import (
    award_development_points,
    award_xp,
    get_development_suggestions_for_character,
    get_or_create_xp_tracker,
)
from world.progression.services.cg_conversion import award_cg_conversion_xp
from world.progression.services.kudos import (
    InsufficientKudosError,
    award_kudos,
    claim_kudos,
    claim_kudos_for_xp,
)
from world.progression.services.scene_integration import (
    award_combat_development,
    award_crafting_development,
    award_scene_development_points,
    award_social_development,
    calculate_automatic_scene_awards,
)
from world.progression.services.scene_rewards import on_scene_finished
from world.progression.services.skill_development import (
    award_check_development,
    calculate_check_dev_points,
)
from world.progression.services.spends import (
    calculate_level_up_requirements,
    check_requirements_for_unlock,
    get_available_unlocks_for_character,
    spend_xp_on_unlock,
)
from world.progression.services.voting import (
    cast_vote,
    get_current_week_start,
    get_or_create_vote_budget,
    get_vote_state,
    get_votes_by_voter,
    increment_scene_bonus,
    remove_vote,
)
from world.progression.types import AwardResult, ClaimResult, KudosXPResult

# For backwards compatibility, make key functions available at package level
__all__ = [
    "AwardResult",
    "ClaimResult",
    "InsufficientKudosError",
    "KudosXPResult",
    "award_cg_conversion_xp",
    "award_check_development",
    "award_combat_development",
    "award_crafting_development",
    "award_development_points",
    "award_kudos",
    "award_scene_development_points",
    "award_social_development",
    "award_xp",
    "calculate_automatic_scene_awards",
    "calculate_check_dev_points",
    "calculate_level_up_requirements",
    "cast_vote",
    "check_requirements_for_unlock",
    "claim_kudos",
    "claim_kudos_for_xp",
    "get_available_unlocks_for_character",
    "get_current_week_start",
    "get_development_suggestions_for_character",
    "get_or_create_vote_budget",
    "get_or_create_xp_tracker",
    "get_vote_state",
    "get_votes_by_voter",
    "increment_scene_bonus",
    "on_scene_finished",
    "remove_vote",
    "spend_xp_on_unlock",
]
