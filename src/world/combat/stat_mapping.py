"""Weapon→stat mapping for combat checks (#2757, #2858, #2879).

The calling system determines which stat a combat check rolls from the
equipped weapon. ``None`` means "use the check's default stat" (no override).

Two mappings. ``GearArchetype`` only distinguishes one-handed from two-handed,
so a rapier and a warhammer both read as ``MELEE_ONE_HAND`` and both roll
agility — the warhammer-wielder gets no mechanical credit for their strength.
``WeaponClass`` (#2879) adds the missing granularity: a weighted
strength/agility blend, so an off-stat weapon is never worthless and every
weapon can express a mix rather than a binary pick.

``WeaponClass`` takes precedence when set. Templates leave it null until
authored, and null falls back to the archetype map — so the finer mapping
rolls out per-template as content lands, with no backfill.
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


def weapon_stat_override(character: CharacterType) -> str | int | None:
    """Return the stat override for the character's equipped weapon, or None.

    Prefers the strongest equipped weapon's ``weapon_class`` (#2879) — returns
    its ``strength_tenths`` (0-10; the check-resolution seam in
    ``world.checks.services`` blends strength/agility at that weight) — and
    falls back to its ``gear_archetype`` (#2757) when the template hasn't been
    classified. Returns ``None`` when the character has no weapon or neither
    map covers it — the caller then uses the check's default stat.
    """
    from world.combat.services import _select_equipped_weapon  # noqa: PLC0415

    inst = _select_equipped_weapon(character)
    if inst is None:
        return None
    weapon_class = inst.template.weapon_class
    if weapon_class is not None:
        return weapon_class.strength_tenths
    return WEAPON_ARCHETYPE_STAT_MAP.get(inst.template.gear_archetype)
