"""
Integration with scenes for awarding development points.

Provides functions to award development points based on scene participation,
actions, and outcomes. Called explicitly by scene completion flows.
"""

from typing import Dict, List

from world.progression.services.awards import award_development_points
from world.progression.types import DevelopmentSource, ProgressionReason
from world.scenes.models import Scene
from world.traits.models import Trait


def award_scene_development_points(
    scene: Scene, participants: List, awards: Dict[str, Dict]
) -> None:
    """
    Award development points to scene participants.

    Args:
        scene: The scene that was completed
        participants: List of characters who participated
        awards: Dict mapping character keys to award details
                Format: {
                    "character_key": {
                        "combat_trait_name": 5,
                        "social_trait_name": 3,
                        "general_trait_name": 1
                    }
                }

    Returns:
        List of DevelopmentTransaction records created
    """
    transactions = []

    for character in participants:
        if character.db_key not in awards:
            continue

        character_awards = awards[character.db_key]

        for trait_name, amount in character_awards.items():
            if amount > 0:
                try:
                    trait = Trait.objects.get(name=trait_name)

                    # Determine source category based on trait
                    if trait.category in ["combat"]:
                        source = DevelopmentSource.COMBAT
                    elif trait.category in ["social", "general"]:
                        source = DevelopmentSource.SOCIAL
                    elif trait.category in ["crafting"]:
                        source = DevelopmentSource.CRAFTING
                    else:
                        source = DevelopmentSource.SCENE

                    transaction = award_development_points(
                        character=character,
                        trait=trait,
                        source=source,
                        amount=amount,
                        scene=scene,
                        reason=ProgressionReason.SCENE_AWARD,
                        description=f"Scene participation: {scene.title or 'Untitled'}",
                    )
                    transactions.append(transaction)
                except Trait.DoesNotExist:
                    # Skip unknown traits
                    continue

    return transactions


def calculate_automatic_scene_awards(
    scene: Scene, participants: List
) -> Dict[str, Dict]:
    """
    Calculate automatic development point awards based on scene content.

    This is a basic implementation that can be expanded with more sophisticated
    analysis of scene actions, outcomes, and character involvement.

    Args:
        scene: The scene to analyze
        participants: List of characters who participated

    Returns:
        Dict of awards in the format expected by award_scene_development_points
    """
    awards = {}

    # Basic participation award - everyone gets 1 point to a trait they can develop
    for character in participants:
        suggested_traits = get_development_suggestions_for_character(character)

        # Award to the first available trait in priority order
        trait_awarded = None
        for source_priority in [DevelopmentSource.SCENE, DevelopmentSource.SOCIAL]:
            if suggested_traits.get(source_priority):
                trait_awarded = suggested_traits[source_priority][0]
                break

        if trait_awarded:
            awards[character.db_key] = {trait_awarded: 1}

    # TODO: Add more sophisticated analysis:
    # - Parse scene logs for action types (combat, social, crafting)
    # - Award specific skill development based on actions taken
    # - Consider scene difficulty/challenge level
    # - Award bonus points for creative/excellent roleplay
    # - Handle teaching/learning interactions

    return awards


def award_combat_development(characters: List, combat_actions: Dict[str, List[str]]):
    """
    Award development points for combat actions.

    Args:
        characters: Characters involved in combat
        combat_actions: Dict mapping character keys to lists of combat actions

    Returns:
        Dict of awards for combat development
    """
    awards = {}

    for character in characters:
        char_key = character.db_key
        if char_key not in combat_actions:
            continue

        actions = combat_actions[char_key]

        # Award points based on action types
        weapon_actions = [
            a
            for a in actions
            if any(
                weapon in a.lower()
                for weapon in ["sword", "bow", "staff", "dagger", "axe"]
            )
        ]
        defense_actions = [
            a
            for a in actions
            if any(
                def_term in a.lower()
                for def_term in ["dodge", "parry", "block", "defend"]
            )
        ]

        combat_awards = {}
        if weapon_actions:
            # Award points to most used weapon type
            weapon_skill = get_most_common_weapon_skill(weapon_actions)
            combat_awards[weapon_skill] = min(len(weapon_actions), 5)  # Cap at 5 points

        if defense_actions:
            combat_awards["dodge"] = min(len(defense_actions), 3)  # Cap at 3 points

        if combat_awards:
            awards[char_key] = combat_awards

    return awards


def award_social_development(characters: List, social_actions: Dict[str, List[str]]):
    """
    Award development points for social actions.

    Args:
        characters: Characters involved in social activity
        social_actions: Dict mapping character keys to lists of social actions

    Returns:
        Dict of awards for social development
    """
    awards = {}

    for character in characters:
        char_key = character.db_key
        if char_key not in social_actions:
            continue

        actions = social_actions[char_key]
        social_awards = {}

        # Award points based on social skill usage
        persuasion_actions = [
            a
            for a in actions
            if any(term in a.lower() for term in ["persuade", "convince", "argue"])
        ]
        charm_actions = [
            a
            for a in actions
            if any(term in a.lower() for term in ["charm", "flirt", "compliment"])
        ]
        leadership_actions = [
            a
            for a in actions
            if any(term in a.lower() for term in ["lead", "command", "inspire"])
        ]

        if persuasion_actions:
            social_awards["persuasion"] = min(len(persuasion_actions), 3)
        if charm_actions:
            social_awards["charm"] = min(len(charm_actions), 3)
        if leadership_actions:
            social_awards["leadership"] = min(len(leadership_actions), 3)

        if social_awards:
            awards[char_key] = social_awards

    return awards


def award_crafting_development(characters: List, crafting_actions: Dict[str, str]):
    """
    Award development points for crafting actions.

    Args:
        characters: Characters involved in crafting
        crafting_actions: Dict mapping character keys to crafting skill names

    Returns:
        Dict of awards for crafting development
    """
    awards = {}

    for character in characters:
        char_key = character.db_key
        if char_key not in crafting_actions:
            continue

        crafting_skill = crafting_actions[char_key]
        awards[char_key] = {crafting_skill: 2}  # 2 points for crafting activity

    return awards


def get_most_common_weapon_skill(weapon_actions: List[str]) -> str:
    """
    Determine the most commonly used weapon skill from actions.

    Args:
        weapon_actions: List of action strings containing weapon references

    Returns:
        Most common weapon skill name
    """
    weapon_counts = {}
    weapon_map = {
        "sword": "swords",
        "bow": "archery",
        "staff": "staves",
        "dagger": "small_weapon",
        "axe": "axes",
        "spear": "spears",
    }

    for action in weapon_actions:
        action_lower = action.lower()
        for weapon, skill in weapon_map.items():
            if weapon in action_lower:
                weapon_counts[skill] = weapon_counts.get(skill, 0) + 1
                break

    if weapon_counts:
        return max(weapon_counts.items(), key=lambda x: x[1])[0]

    return "small_weapon"  # Default fallback


def get_development_suggestions_for_character(character) -> Dict[str, List[str]]:
    """
    Get development suggestions for a character based on their current traits and unlocks.

    Args:
        character: Character to analyze

    Returns:
        Dict mapping development sources to suggested trait names
    """
    from world.progression.services.awards import (
        get_development_suggestions_for_character,
    )

    # Use the main awards service function
    return get_development_suggestions_for_character(character)
