"""Effective soak and resistance for an opponent."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import OpponentTier
from world.combat.models import CombatOpponent
from world.combat.services.damage.vulnerability import _is_vulnerable

if TYPE_CHECKING:
    from world.conditions.models import DamageType


# Tiers whose soak is a wall that stands against every damage type (#5026, owner ruling):
# a boss's defenses must be broken, and a Hero Killer's armor stops every type like a boss's.
_WALLED_TIERS = frozenset({OpponentTier.BOSS, OpponentTier.HERO_KILLER})


def has_wall(opponent: CombatOpponent) -> bool:
    """Whether ``opponent``'s soak is a wall that stands against every damage type (#5026).

    A boss or a Hero Killer, or any opponent with a probing threshold (the wall the
    existing probing, combos, ``wall_breaker_combo`` and break bar exist to break). Every
    other opponent's soak stops Physical only; its other protections are resistances.
    """
    return opponent.tier in _WALLED_TIERS or opponent.probing_threshold is not None


def _effective_soak_for_opponent(
    opponent: CombatOpponent, bypass_soak: bool, damage_type: DamageType | None = None
) -> int:
    """Return the effective soak value, bypassed by bypass_soak or vulnerability.

    An ordinary opponent's soak stops a Physical hit only (#5026); a walled opponent's
    (``has_wall``) stops every type. ``damage_type`` None is a Physical hit.
    """
    if bypass_soak or _is_vulnerable(opponent):
        return 0
    from world.combat.services.equipment.armor_soak import is_physical  # noqa: PLC0415

    if not has_wall(opponent) and not is_physical(damage_type):
        return 0
    return opponent.soak_value


def target_soak_of(opponent: CombatOpponent, damage_type: DamageType | None = None) -> int:
    """The soak that stands against a hit of ``damage_type`` on ``opponent``, for a derived
    amount (#4892). None is a Physical hit.

    An ordinary opponent's ``soak_value`` against a Physical hit (#5026), 0 while it is
    vulnerable; a swarm has no soak; a duel mirror's is the mirrored player's worn-armor
    soak against that type, read without wearing it. Thread damage reduction and the
    mitigation leak are not soak and are left out.
    """
    if opponent.tier == OpponentTier.SWARM and opponent.swarm_count is not None:
        return 0
    if opponent.is_duel_mirror:
        from world.combat.services.equipment.armor_soak import (  # noqa: PLC0415
            equipped_armor_soak,
        )

        return equipped_armor_soak(
            opponent.mirrors_participant.character_sheet.character, damage_type
        )
    return _effective_soak_for_opponent(opponent, bypass_soak=False, damage_type=damage_type)


def _duel_mirror_pc_reduction(
    opponent: CombatOpponent,
    damage: int,
    *,
    armor_soak_applies: bool,
    damage_type: DamageType | None = None,
) -> int:
    """Reduce a duel mirror's hit by the mirrored PC's own thread DR and armor soak (#4758).

    A duelist is hit through her mirror, which carries no soak of its own. The PC path
    (``apply_damage_to_participant``) applies the thread damage reduction and worn-armor
    soak; the mirror must apply the same two, or an armored duelist takes the full hit.
    Non-mirror opponents pass through unchanged.
    """
    if not opponent.is_duel_mirror or damage <= 0:
        return damage
    from world.combat.services.equipment.armor_soak import (  # noqa: PLC0415
        apply_equipped_armor_soak,
    )
    from world.magic.services import apply_damage_reduction_from_threads  # noqa: PLC0415

    character = opponent.mirrors_participant.character_sheet.character
    damage = apply_damage_reduction_from_threads(character, damage)
    if armor_soak_applies:
        damage = apply_equipped_armor_soak(character, damage, damage_type)
    return damage


def _effective_resistance_for_opponent(
    opponent: CombatOpponent, damage_type: DamageType | None, resistance_shift: int = 0
) -> int:
    """Return signed typed resistance after break-bar override and per-hit shift."""
    if damage_type is None:
        return 0
    resistance = 0
    if opponent.objectdb is not None and not _is_vulnerable(opponent):
        resistance = opponent.objectdb.conditions.resistance_modifier(damage_type)
    return resistance - resistance_shift
