"""Elevation bonus for positioned combatants."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import ELEVATION_ADVANTAGE_TARGET_NAME
from world.combat.services.equipment.combat_target_bonus import _combat_target_bonus

if TYPE_CHECKING:
    from world.areas.positioning.models import Position
    from world.character_sheets.models import CharacterSheet


def elevation_bonus(
    attacker_sheet: CharacterSheet, attacker_pos: Position, target_pos: Position
) -> int:
    """Flat to-hit bonus when attacker is elevated/aerial and target is not.

    Returns 0 in all other cases (both elevated, both ground, attacker
    ground / target elevated). Offensive-only — no penalty for firing up.
    The magnitude comes from the 'elevation_advantage' ModifierTarget
    (staff-authored via CharacterModifier).
    """
    from world.areas.positioning.constants import PositionKind  # noqa: PLC0415

    elevated_kinds = {PositionKind.ELEVATED, PositionKind.AERIAL}
    if attacker_pos.kind not in elevated_kinds:
        return 0
    if target_pos.kind in elevated_kinds:
        return 0
    return _combat_target_bonus(attacker_sheet, ELEVATION_ADVANTAGE_TARGET_NAME)
