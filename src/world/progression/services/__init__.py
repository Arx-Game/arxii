"""
Progression services package.

This package organizes progression services into logical modules:
- awards: Functions for awarding XP and development points
- spends: Functions for spending XP on unlocks
- scene_integration: Scene-based reward integration
"""

# Import key functions from submodules for convenience
from world.progression.services.awards import (  # noqa: I252
    award_development_points,
    award_xp,
    get_development_suggestions_for_character,
    get_or_create_xp_tracker,
)
from world.progression.services.scene_integration import (  # noqa: I252
    award_combat_development,
    award_crafting_development,
    award_scene_development_points,
    award_social_development,
    calculate_automatic_scene_awards,
)
from world.progression.services.spends import (  # noqa: I252
    calculate_level_up_requirements,
    check_requirements_for_unlock,
    get_available_unlocks_for_character,
    spend_xp_on_unlock,
)

# For backwards compatibility, make key functions available at package level
__all__ = [
    # Awards
    "get_or_create_xp_tracker",
    "award_xp",
    "award_development_points",
    "get_development_suggestions_for_character",
    # Spends
    "spend_xp_on_unlock",
    "check_requirements_for_unlock",
    "get_available_unlocks_for_character",
    "calculate_level_up_requirements",
    # Scene Integration
    "award_scene_development_points",
    "calculate_automatic_scene_awards",
    "award_combat_development",
    "award_social_development",
    "award_crafting_development",
]
