"""
Goals Service Functions

Service layer for goal bonus calculations with percentage modifiers.
"""

from typing import TYPE_CHECKING

from world.goals.models import CharacterGoal
from world.mechanics.models import CharacterModifier, ModifierType

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


def get_goal_bonus(
    character: "CharacterSheet",
    domain_name: str,
) -> int:
    """
    Get the goal bonus for a specific domain, applying percentage modifiers.

    Base bonus = CharacterGoal.points for that domain.
    Final bonus = base * (1 + percentage_modifiers/100).

    Percentage modifiers come from:
    - goal_percent/all: applies to all goal bonuses
    - goal_percent/<domain>: applies to specific domain only

    Args:
        character: CharacterSheet instance
        domain_name: Goal domain name (e.g., "Needs", "Standing")

    Returns:
        Final goal bonus as integer (truncated)
    """
    # Get base goal points for this domain
    try:
        goal = CharacterGoal.objects.get(
            character=character.character,
            domain__name__iexact=domain_name,
            domain__category__name="goal",
        )
        base_points = goal.points
    except CharacterGoal.DoesNotExist:
        base_points = 0

    if base_points == 0:
        return 0

    # Get percentage modifiers
    total_percent = _get_goal_percent_modifier(character, domain_name)

    # Apply percentage: final = base * (1 + percent/100)
    multiplier = 1 + (total_percent / 100)
    return int(base_points * multiplier)


def _get_goal_percent_modifier(
    character: "CharacterSheet",
    domain_name: str,
) -> int:
    """
    Get total percentage modifier for a goal domain.

    Combines:
    - goal_percent/all modifiers (apply to all goals)
    - goal_percent/<domain_name> modifiers (domain-specific)

    Args:
        character: CharacterSheet instance
        domain_name: Goal domain name

    Returns:
        Total percentage modifier (e.g., 150 means +150%)
    """
    total_percent = 0

    # Get "all" goal percent modifier
    all_modifiers = CharacterModifier.objects.filter(
        character=character,
        source__distinction_effect__target__category__name="goal_percent",
        source__distinction_effect__target__name="all",
    )
    total_percent += sum(m.value for m in all_modifiers)

    # Get domain-specific percent modifier
    domain_modifiers = CharacterModifier.objects.filter(
        character=character,
        source__distinction_effect__target__category__name="goal_percent",
        source__distinction_effect__target__name__iexact=domain_name,
    )
    total_percent += sum(m.value for m in domain_modifiers)

    return total_percent


def get_total_goal_points(character: "CharacterSheet") -> int:
    """
    Get the total goal points available for a character to distribute.

    Base is 30, plus any goal_points/total_points modifiers from distinctions.

    Args:
        character: CharacterSheet instance

    Returns:
        Total goal points available (base 30 + modifiers)
    """
    base_points = 30

    # Get goal_points/total_points modifiers
    bonus_modifiers = CharacterModifier.objects.filter(
        character=character,
        source__distinction_effect__target__category__name="goal_points",
        source__distinction_effect__target__name="total_points",
    )
    bonus = sum(m.value for m in bonus_modifiers)

    return base_points + bonus


def get_goal_bonuses_breakdown(
    character: "CharacterSheet",
) -> dict[str, dict]:
    """
    Get breakdown of all goal bonuses for a character.

    Returns:
        Dict mapping domain name to:
        - base_points: Raw points allocated
        - percent_modifier: Total percentage modifier
        - final_bonus: Calculated bonus after percentage
    """
    # Get all goal domains
    goal_domains = ModifierType.objects.filter(
        category__name="goal",
        is_active=True,
    )

    breakdown = {}
    for domain in goal_domains:
        base_points = 0
        try:
            goal = CharacterGoal.objects.get(
                character=character.character,
                domain=domain,
            )
            base_points = goal.points
        except CharacterGoal.DoesNotExist:
            pass

        percent_modifier = _get_goal_percent_modifier(character, domain.name)
        multiplier = 1 + (percent_modifier / 100) if base_points > 0 else 1
        final_bonus = int(base_points * multiplier) if base_points > 0 else 0

        breakdown[domain.name] = {
            "base_points": base_points,
            "percent_modifier": percent_modifier,
            "final_bonus": final_bonus,
        }

    return breakdown
