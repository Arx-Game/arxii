"""Effective soak and resistance for an opponent."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.models import CombatOpponent
from world.combat.services.damage.vulnerability import _is_vulnerable

if TYPE_CHECKING:
    from world.conditions.models import DamageType


def _effective_soak_for_opponent(opponent: CombatOpponent, bypass_soak: bool) -> int:
    """Return the effective soak value, bypassed by bypass_soak or vulnerability."""
    if bypass_soak or _is_vulnerable(opponent):
        return 0
    return opponent.soak_value


def _effective_resistance_for_opponent(
    opponent: CombatOpponent, damage_type: DamageType | None, resistance_shift: int = 0
) -> int:
    """Return damage-type resistance, bypassed during vulnerability window."""
    if damage_type is None:
        return 0
    resistance = 0
    if opponent.objectdb is not None and not _is_vulnerable(opponent):
        resistance = opponent.objectdb.conditions.resistance_modifier(damage_type)
    return resistance - resistance_shift
