"""Action fatigue cost pipeline.

Orchestrates the full action pipeline: apply fatigue cost, compute effort/fatigue
modifiers for checks, and handle collapse risk.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from django.db import transaction

from world.character_sheets.models import CharacterSheet
from world.fatigue.constants import EFFORT_CHECK_MODIFIER, EffortLevel
from world.fatigue.services import (
    apply_fatigue,
    attempt_endurance_check,
    attempt_power_through,
    get_fatigue_penalty,
    get_fatigue_zone,
    should_check_collapse,
)
from world.fatigue.types import ActionResult


def execute_action_with_fatigue(
    character_sheet: CharacterSheet,
    fatigue_category: str,
    base_fatigue_cost: int,
    effort_level: str,
    check_fn: Callable[[int, int], Any] | None = None,
) -> ActionResult:
    """Execute an action with fatigue costs and effort modifiers.

    Steps:
        1. Calculate fatigue penalty for the check (from current zone, before cost).
        2. Calculate effort modifier for the check.
        3. Apply fatigue cost (with effort multiplier).
        4. If check_fn provided, execute it with (effort_modifier, fatigue_penalty).
        5. Check collapse risk (based on zone AFTER fatigue applied).
        6. Return result with all details.

    Args:
        character_sheet: The character's sheet.
        fatigue_category: FatigueCategory value (physical/social/mental).
        base_fatigue_cost: Base fatigue cost of the action.
        effort_level: EffortLevel value.
        check_fn: Optional callable(effort_modifier, fatigue_penalty) -> check result.

    Returns:
        ActionResult with fatigue, collapse, and check details.

    Raises:
        ValueError: If effort_level is not a valid EffortLevel.
    """
    EffortLevel(effort_level)  # Validates the string is a valid choice

    with transaction.atomic():
        return _execute_action_with_fatigue(
            character_sheet, fatigue_category, base_fatigue_cost, effort_level, check_fn
        )


def _execute_action_with_fatigue(
    character_sheet: CharacterSheet,
    fatigue_category: str,
    base_fatigue_cost: int,
    effort_level: str,
    check_fn: Callable[[int, int], Any] | None = None,
) -> ActionResult:
    """Inner implementation wrapped in a transaction by execute_action_with_fatigue."""
    # 1. Fatigue penalty from current zone (before applying new cost)
    fatigue_penalty = get_fatigue_penalty(character_sheet, fatigue_category)

    # 2. Effort modifier for the check
    effort_modifier = EFFORT_CHECK_MODIFIER.get(effort_level, 0)

    # 3. Apply fatigue cost
    fatigue_applied = apply_fatigue(
        character_sheet, fatigue_category, base_fatigue_cost, effort_level
    )

    # 4. Execute check if provided
    check_result = None
    if check_fn is not None:
        check_result = check_fn(effort_modifier, fatigue_penalty)

    # 5. Collapse risk (based on zone AFTER fatigue applied)
    fatigue_zone = get_fatigue_zone(character_sheet, fatigue_category)
    collapse_triggered = should_check_collapse(character_sheet, fatigue_category, effort_level)

    collapsed = False
    powered_through = False
    strain_damage = 0

    if collapse_triggered:
        passed_endurance = attempt_endurance_check(character_sheet, fatigue_category)
        if not passed_endurance:
            power_success, strain = attempt_power_through(character_sheet, fatigue_category)
            strain_damage = strain
            if power_success:
                powered_through = True
            else:
                collapsed = True

    return ActionResult(
        fatigue_applied=fatigue_applied,
        effort_level=effort_level,
        fatigue_zone=fatigue_zone,
        collapse_triggered=collapse_triggered,
        collapsed=collapsed,
        powered_through=powered_through,
        strain_damage=strain_damage,
        check_result=check_result,
    )
