"""
Progression services package.

This package organizes progression services into logical modules:
- awards: Functions for awarding XP and development points
- spends: Functions for spending XP on unlocks
- scene_integration: Scene-based reward integration
"""

# Import key functions from submodules for convenience
from world.progression.services.awards import (
    award_development_points,
    award_xp,
    get_development_suggestions_for_character,
    get_or_create_xp_tracker,
)
from world.progression.services.scene_integration import (
    award_combat_development,
    award_crafting_development,
    award_scene_development_points,
    award_social_development,
    calculate_automatic_scene_awards,
)
from world.progression.services.spends import (
    calculate_level_up_requirements,
    check_requirements_for_unlock,
    get_available_unlocks_for_character,
    spend_xp_on_unlock,
)

# For backwards compatibility, make key functions available at package level
__all__ = [
    "award_combat_development",
    "award_crafting_development",
    "award_development_points",
    # Scene Integration
    "award_scene_development_points",
    "award_social_development",
    "award_xp",
    "calculate_automatic_scene_awards",
    "calculate_level_up_requirements",
    "check_requirements_for_unlock",
    "get_available_unlocks_for_character",
    "get_development_suggestions_for_character",
    # Awards
    "get_or_create_xp_tracker",
    # Spends
    "spend_xp_on_unlock",
]
