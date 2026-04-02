"""
Fatigue system service functions.

Handles capacity calculation, zone detection, penalty lookup, fatigue application,
collapse checks, and rest mechanics.
"""

from __future__ import annotations

import random

from django.db import transaction

from world.action_points.models import ActionPointPool
from world.character_creation.constants import STAT_MAX_VALUE
from world.character_sheets.models import CharacterSheet
from world.fatigue.constants import (
    CAPACITY_STAT_MULTIPLIER,
    CAPACITY_WILLPOWER_MULTIPLIER,
    COLLAPSE_RISK_ZONES,
    EFFORT_COST_MULTIPLIER,
    FATIGUE_ENDURANCE_STAT,
    MIN_FATIGUE_COST,
    REST_AP_COST,
    WELL_RESTED_MULTIPLIER,
    ZONE_PENALTIES,
    ZONE_THRESHOLDS,
    FatigueCategory,
    FatigueZone,
)
from world.fatigue.models import FatiguePool
from world.fatigue.types import RestResult
from world.traits.constants import PrimaryStat


def get_or_create_fatigue_pool(character_sheet: CharacterSheet) -> FatiguePool:
    """Get or create a FatiguePool for a character sheet."""
    pool, _ = FatiguePool.objects.get_or_create(character=character_sheet)
    return pool


def _get_display_stat_value(character_sheet: CharacterSheet, stat_name: str) -> int:
    """Get a stat's display value (1-5 scale) from the trait handler.

    Handles both storage conventions:
    - Legacy characters: values stored as 10-50 (internal scale), divided by 10
    - CG-simplified characters: values stored as 1-5 (display scale), used directly

    Values > 5 are assumed to be internal scale. Values 1-5 are display scale.
    """
    raw_value = character_sheet.character.traits.get_trait_value(stat_name)
    if raw_value > STAT_MAX_VALUE:
        return raw_value // 10
    return raw_value


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
    willpower_value = _get_display_stat_value(character_sheet, PrimaryStat.WILLPOWER.value)

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
    pool = get_or_create_fatigue_pool(character_sheet)
    current = pool.get_current(category)

    if capacity <= 0:
        return 100.0 if current > 0 else 0.0

    return (current / capacity) * 100


def _zone_from_percentage(percentage: float) -> str:
    """Return the FatigueZone for a given fatigue percentage.

    Args:
        percentage: Fatigue as a percentage of capacity.

    Returns:
        FatigueZone value string.
    """
    for zone, _low, high in ZONE_THRESHOLDS:
        if high is None:
            return zone
        if percentage <= high:
            return zone

    return FatigueZone.EXHAUSTED


def get_fatigue_zone(character_sheet: CharacterSheet, category: str) -> str:
    """Return the FatigueZone based on current fatigue percentage.

    Args:
        character_sheet: The character's sheet.
        category: FatigueCategory value.

    Returns:
        FatigueZone value string.
    """
    percentage = get_fatigue_percentage(character_sheet, category)
    return _zone_from_percentage(percentage)


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

    Collapse risk depends on effort level:
    - VERY_LOW / LOW: never collapses
    - MEDIUM: collapses only when EXHAUSTED (100%+)
    - HIGH / EXTREME: collapses when OVEREXERTED (81%+) or EXHAUSTED

    Args:
        character_sheet: The character's sheet.
        category: FatigueCategory value.
        effort_level: EffortLevel value.

    Returns:
        True if collapse check should be made.
    """
    min_collapse_zone = COLLAPSE_RISK_ZONES.get(effort_level)
    if min_collapse_zone is None:
        return False

    zone = get_fatigue_zone(character_sheet, category)
    zone_order = [
        FatigueZone.FRESH,
        FatigueZone.STRAINED,
        FatigueZone.TIRED,
        FatigueZone.OVEREXERTED,
        FatigueZone.EXHAUSTED,
    ]
    return zone_order.index(zone) >= zone_order.index(min_collapse_zone)


def attempt_endurance_check(character_sheet: CharacterSheet, category: str) -> bool:
    """Roll endurance stat vs fatigue to stay conscious.

    Formula: d100 + (endurance_stat * 10) vs (fatigue_percentage - 60) * 3
    Roll of 1 always fails. Roll of 100 always succeeds.
    High endurance (5-10) makes passing easier at moderate fatigue levels.

    TODO: Migrate to the unified dice roll resolution system when built.

    Args:
        character_sheet: The character's sheet.
        category: FatigueCategory value.

    Returns:
        True if character stays conscious.
    """
    endurance_stat_name = FATIGUE_ENDURANCE_STAT[category]
    endurance_value = _get_display_stat_value(character_sheet, endurance_stat_name)

    percentage = get_fatigue_percentage(character_sheet, category)
    target = int((percentage - 60) * 3)

    roll = random.randint(1, 100)  # noqa: S311
    if roll == 1:
        return False  # Critical failure — always collapse
    if roll == 100:  # noqa: PLR2004
        return True  # Critical success — always stay conscious

    return (roll + endurance_value * 10) > target


def attempt_power_through(
    character_sheet: CharacterSheet,
    category: str,
) -> tuple[bool, int]:
    """Willpower check to stay conscious after failing endurance check.

    Formula: d100 + (willpower * 10) vs 50 + (strain_damage * 3)
    Roll of 1 always fails. Roll of 100 always succeeds.
    Intensity bonuses (combat/high-stakes) should be added as modifiers
    when the modifier system integration is built.

    TODO: Migrate to the unified dice roll resolution system when built.
    TODO: Add intensity bonus from combat/dramatic context.

    Args:
        character_sheet: The character's sheet.
        category: FatigueCategory value.

    Returns:
        Tuple of (succeeded, strain_damage). Strain damage is applied
        regardless of success and scales with over-capacity ratio.
    """
    willpower_value = _get_display_stat_value(character_sheet, PrimaryStat.WILLPOWER.value)

    capacity = get_fatigue_capacity(character_sheet, category)
    pool = get_or_create_fatigue_pool(character_sheet)
    current = pool.get_current(category)

    # Strain damage scales with how far past capacity
    over_ratio = max(0, (current - capacity)) / max(1, capacity)
    strain_damage = max(1, int(over_ratio * 10))

    roll = random.randint(1, 100)  # noqa: S311
    if roll == 1:
        return False, strain_damage  # Critical failure
    if roll == 100:  # noqa: PLR2004
        return True, strain_damage  # Critical success

    target = 50 + (strain_damage * 3)
    succeeded = (roll + willpower_value * 10) > target

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


@transaction.atomic
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
    # TODO: Add location check — rest should only be available at character's home
    pool, _ = FatiguePool.objects.select_for_update().get_or_create(character=character_sheet)

    if pool.rested_today:
        return RestResult(success=False, message="You have already rested today.")

    ap_pool = ActionPointPool.get_or_create_for_character(character_sheet.character)
    if not ap_pool.spend(REST_AP_COST):
        return RestResult(
            success=False,
            message=f"Not enough action points. Resting costs {REST_AP_COST} AP.",
        )

    pool.well_rested = True
    pool.rested_today = True
    pool.save()

    return RestResult(
        success=True,
        message="You rest and feel refreshed. You will have increased stamina tomorrow.",
    )


def get_full_status(character_sheet: CharacterSheet) -> dict:
    """Get fatigue status for all three categories in one pass.

    Args:
        character_sheet: The character's sheet.

    Returns:
        Dictionary with per-category status and global flags.
    """
    pool = get_or_create_fatigue_pool(character_sheet)
    status: dict = {}
    for category in FatigueCategory:
        cat = category.value
        capacity = get_fatigue_capacity(character_sheet, cat)
        current = pool.get_current(cat)
        pct = (current / capacity * 100) if capacity > 0 else (100.0 if current > 0 else 0.0)
        zone = _zone_from_percentage(pct)
        status[cat] = {
            "current": current,
            "capacity": capacity,
            "percentage": round(pct, 1),
            "zone": zone,
        }
    status["well_rested"] = pool.well_rested
    status["rested_today"] = pool.rested_today
    return status
