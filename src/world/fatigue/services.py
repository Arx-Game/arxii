"""
Fatigue system service functions.

Handles capacity calculation, zone detection, penalty lookup, fatigue application,
collapse checks, and rest mechanics.
"""

from __future__ import annotations

from dataclasses import dataclass
import random

from world.action_points.models import ActionPointPool
from world.character_sheets.models import CharacterSheet
from world.fatigue.constants import (
    CAPACITY_STAT_MULTIPLIER,
    CAPACITY_WILLPOWER_MULTIPLIER,
    COLLAPSE_RISK_EFFORT_LEVELS,
    EFFORT_COST_MULTIPLIER,
    FATIGUE_ENDURANCE_STAT,
    MIN_FATIGUE_COST,
    REST_AP_COST,
    WELL_RESTED_MULTIPLIER,
    ZONE_PENALTIES,
    ZONE_THRESHOLDS,
    FatigueZone,
)
from world.fatigue.models import FatiguePool


def get_or_create_fatigue_pool(character_sheet: CharacterSheet) -> FatiguePool:
    """Get or create a FatiguePool for a character sheet."""
    pool, _ = FatiguePool.objects.get_or_create(character=character_sheet)
    return pool


def _get_display_stat_value(character_sheet: CharacterSheet, stat_name: str) -> int:
    """Get a stat's display value (1-5 scale) from the trait handler.

    The trait handler stores values internally at 10x scale (10-50).
    This divides by 10 to get the display value used in formulas.
    """
    internal_value = character_sheet.character.traits.get_trait_value(stat_name)
    return internal_value // 10


def get_fatigue_capacity(character_sheet: CharacterSheet, category: str) -> int:
    """Calculate max fatigue capacity for a category.

    Formula: endurance_stat * CAPACITY_STAT_MULTIPLIER + willpower * CAPACITY_WILLPOWER_MULTIPLIER
    If well_rested: multiply by WELL_RESTED_MULTIPLIER (1.5)

    Args:
        character_sheet: The character's sheet.
        category: FatigueCategory value (physical/social/mental).

    Returns:
        Integer fatigue capacity.
    """
    endurance_stat_name = FATIGUE_ENDURANCE_STAT[category]
    endurance_value = _get_display_stat_value(character_sheet, endurance_stat_name)
    willpower_value = _get_display_stat_value(character_sheet, "willpower")

    base_capacity = (
        endurance_value * CAPACITY_STAT_MULTIPLIER + willpower_value * CAPACITY_WILLPOWER_MULTIPLIER
    )

    pool = get_or_create_fatigue_pool(character_sheet)
    if pool.well_rested:
        return int(base_capacity * WELL_RESTED_MULTIPLIER)

    return base_capacity


def get_fatigue_percentage(character_sheet: CharacterSheet, category: str) -> float:
    """Return current fatigue as a percentage of capacity.

    Args:
        character_sheet: The character's sheet.
        category: FatigueCategory value.

    Returns:
        Percentage (0.0 to potentially >100.0 if over capacity).
    """
    capacity = get_fatigue_capacity(character_sheet, category)
    if capacity <= 0:
        return 0.0

    pool = get_or_create_fatigue_pool(character_sheet)
    current = pool.get_current(category)
    return (current / capacity) * 100


def get_fatigue_zone(character_sheet: CharacterSheet, category: str) -> str:
    """Return the FatigueZone based on current fatigue percentage.

    Args:
        character_sheet: The character's sheet.
        category: FatigueCategory value.

    Returns:
        FatigueZone value string.
    """
    percentage = get_fatigue_percentage(character_sheet, category)

    for zone, low, high in ZONE_THRESHOLDS:
        if high is None:
            if percentage >= low:
                return zone
        elif low <= percentage <= high:
            return zone

    return FatigueZone.FRESH


def get_fatigue_penalty(character_sheet: CharacterSheet, category: str) -> int:
    """Return the check penalty for the current fatigue zone.

    Args:
        character_sheet: The character's sheet.
        category: FatigueCategory value.

    Returns:
        Negative integer penalty (0 for FRESH).
    """
    zone = get_fatigue_zone(character_sheet, category)
    return ZONE_PENALTIES[zone]


def apply_fatigue(
    character_sheet: CharacterSheet,
    category: str,
    base_cost: int,
    effort_level: str,
) -> int:
    """Add fatigue to the pool.

    Calculates actual cost from base_cost * effort multiplier. Fatigue can
    exceed capacity (no cap).

    Args:
        character_sheet: The character's sheet.
        category: FatigueCategory value.
        base_cost: Base fatigue cost of the action.
        effort_level: EffortLevel value.

    Returns:
        The actual fatigue cost applied.
    """
    multiplier = EFFORT_COST_MULTIPLIER[effort_level]
    actual_cost = max(MIN_FATIGUE_COST, int(base_cost * multiplier))

    pool = get_or_create_fatigue_pool(character_sheet)
    current = pool.get_current(category)
    pool.set_current(category, current + actual_cost)
    pool.save()

    return actual_cost


def should_check_collapse(
    character_sheet: CharacterSheet,
    category: str,
    effort_level: str,
) -> bool:
    """Return True if a collapse check is needed.

    Collapse risk applies only for HIGH and EXTREME effort when
    in the OVEREXERTED or EXHAUSTED zone. VERY_LOW, LOW, and MEDIUM
    are always safe from collapse.

    Args:
        character_sheet: The character's sheet.
        category: FatigueCategory value.
        effort_level: EffortLevel value.

    Returns:
        True if collapse check should be made.
    """
    if effort_level not in COLLAPSE_RISK_EFFORT_LEVELS:
        return False

    zone = get_fatigue_zone(character_sheet, category)
    return zone in (FatigueZone.OVEREXERTED, FatigueZone.EXHAUSTED)


def attempt_endurance_check(character_sheet: CharacterSheet, category: str) -> bool:
    """Roll endurance stat vs fatigue to stay conscious.

    Difficulty scales with how far past the overexerted threshold the
    character is. The endurance stat for the category is rolled against
    a target that increases with fatigue percentage.

    Args:
        character_sheet: The character's sheet.
        category: FatigueCategory value.

    Returns:
        True if character stays conscious.
    """
    endurance_stat_name = FATIGUE_ENDURANCE_STAT[category]
    endurance_value = _get_display_stat_value(character_sheet, endurance_stat_name)

    percentage = get_fatigue_percentage(character_sheet, category)
    # Difficulty scales: at 81% (just overexerted) it's easy, at 150%+ it's very hard
    # Target number = percentage - 60 (so at 81% target is 21, at 100% target is 40)
    target = int(percentage - 60)

    # Roll: endurance * 10 + d100 vs target * 10
    # Simplified: roll 1-100 + (endurance * 10) must beat target * 10
    roll = random.randint(1, 100) + (endurance_value * 10)  # noqa: S311
    return roll > (target * 10)


def attempt_power_through(
    character_sheet: CharacterSheet,
    category: str,
) -> tuple[bool, int]:
    """Willpower check to stay conscious after failing endurance check.

    Args:
        character_sheet: The character's sheet.
        category: FatigueCategory value.

    Returns:
        Tuple of (succeeded, strain_damage). Strain damage is applied
        regardless of success and scales with over-capacity ratio.
    """
    willpower_value = _get_display_stat_value(character_sheet, "willpower")

    capacity = get_fatigue_capacity(character_sheet, category)
    pool = get_or_create_fatigue_pool(character_sheet)
    current = pool.get_current(category)

    # Strain damage scales with how far past capacity
    over_ratio = max(0, (current - capacity)) / max(1, capacity)
    strain_damage = max(1, int(over_ratio * 10))

    # Willpower check: roll 1-100 + (willpower * 10) must beat 50 + strain * 10
    roll = random.randint(1, 100) + (willpower_value * 10)  # noqa: S311
    target = 50 + (strain_damage * 10)
    succeeded = roll > target

    return succeeded, strain_damage


def reset_fatigue(character_sheet: CharacterSheet) -> None:
    """Reset all fatigue pools to 0.

    Clears dawn_deferred flag and resets rested_today. If the character
    was well_rested, the bonus was already factored into capacity during
    the day; this clears it for the next day.
    """
    pool = get_or_create_fatigue_pool(character_sheet)
    pool.physical_current = 0
    pool.social_current = 0
    pool.mental_current = 0
    pool.dawn_deferred = False
    pool.rested_today = False
    pool.well_rested = False
    pool.save()


@dataclass
class RestResult:
    """Result of a rest attempt."""

    success: bool
    message: str


def rest(character_sheet: CharacterSheet) -> RestResult:
    """Spend AP to rest, gaining well_rested for the next dawn reset.

    Checks:
    - Character has not already rested today
    - Character can afford the AP cost

    Args:
        character_sheet: The character's sheet.

    Returns:
        RestResult with success flag and message.
    """
    pool = get_or_create_fatigue_pool(character_sheet)

    if pool.rested_today:
        return RestResult(success=False, message="You have already rested today.")

    ap_pool = ActionPointPool.get_or_create_for_character(character_sheet.character)
    if not ap_pool.can_afford(REST_AP_COST):
        return RestResult(
            success=False,
            message=f"Not enough action points. Resting costs {REST_AP_COST} AP.",
        )

    if not ap_pool.spend(REST_AP_COST):
        return RestResult(success=False, message="Failed to spend action points.")

    pool.well_rested = True
    pool.rested_today = True
    pool.save()

    return RestResult(
        success=True,
        message="You rest and feel refreshed. You will have increased stamina tomorrow.",
    )
