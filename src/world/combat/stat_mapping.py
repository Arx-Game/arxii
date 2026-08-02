"""Weapon→stat mapping for combat checks (#2757, #2858, #2879).

The calling system determines which stat a combat check rolls from the
equipped weapon. This is authored content — a simple mapping to a stat
name. ``None`` means "use the check's default stat" (no override).

``GearArchetype`` only distinguishes one-handed from two-handed, so a
rapier and a warhammer both read as ``MELEE_ONE_HAND`` and both roll
agility — the warhammer-wielder gets no mechanical credit for their
strength. #2858's small/medium/heavy ``WeaponClass`` override, meant to
add that missing granularity, was retired by #2879 in favor of a proper
``WeaponClass`` lookup table (``world.items.models.WeaponClass``,
``strength_tenths``) that blends strength/agility by weight instead of
picking one stat wholesale.

Stopgap (Task 1 of #2879's plan): ``ItemTemplate.weapon_class`` is now a
nullable FK to that table, but this module doesn't consume it yet — every
weapon currently falls back to the archetype map below. The blend
substitution (``weapon_class.strength_tenths``) lands in a follow-up task
that also threads an ``int`` ``stat_override`` through
``world.checks.services``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.items.constants import GearArchetype

if TYPE_CHECKING:
    from typeclasses.characters import Character as CharacterType

# GearArchetype → stat name. None = use the check's default stat.
WEAPON_ARCHETYPE_STAT_MAP: dict[str, str | None] = {
    GearArchetype.MELEE_ONE_HAND: "agility",
    GearArchetype.MELEE_TWO_HAND: "strength",
    GearArchetype.RANGED: "agility",
    GearArchetype.THROWN: "strength",
    GearArchetype.LANCE: "strength",
    GearArchetype.OTHER: None,
}

# Defense is always agility-based (dodging/parrying, not striking).
DEFENSE_STAT: str = "agility"


def weapon_stat_override(character: CharacterType) -> str | None:
    """Return the stat name for the character's equipped weapon, or None.

    Uses the strongest equipped weapon's ``gear_archetype`` (#2757).
    ``weapon_class`` (#2879) isn't consumed here yet — see the module
    docstring. Returns ``None`` when the character has no weapon or the
    archetype map doesn't cover it — the caller then uses the check's
    default stat.
    """
    from world.combat.services import _select_equipped_weapon  # noqa: PLC0415

    inst = _select_equipped_weapon(character)
    if inst is None:
        return None
    return WEAPON_ARCHETYPE_STAT_MAP.get(inst.template.gear_archetype)
