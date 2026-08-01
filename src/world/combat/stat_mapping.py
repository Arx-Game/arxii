"""Weapon→stat mapping for combat checks (#2757, #2858).

The calling system determines which stat a combat check rolls from the
equipped weapon. This is authored content — a simple mapping to a stat
name. ``None`` means "use the check's default stat" (no override).

Two mappings, coarse and fine. ``GearArchetype`` only distinguishes
one-handed from two-handed, so a rapier and a warhammer both read as
``MELEE_ONE_HAND`` and both roll agility — the warhammer-wielder gets no
mechanical credit for their strength. ``WeaponClass`` (#2858) adds the
missing granularity: a template tagged ``heavy`` rolls strength whatever
its archetype, so a heavy crossbow and a shortbow can differ too.

``WeaponClass`` takes precedence when set. Templates leave it blank until
authored, and blank falls back to the archetype map — so the finer
mapping rolls out per-template as content lands, with no backfill.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.items.constants import GearArchetype, WeaponClass

if TYPE_CHECKING:
    from typeclasses.characters import Character as CharacterType

# WeaponClass → stat name. Checked before the archetype map (#2858).
# Only heavy weapons roll strength: medium keeps the one-handed→agility
# behavior #2757 established, so tagging a template `medium` is a no-op.
WEAPON_CLASS_STAT_MAP: dict[str, str] = {
    WeaponClass.SMALL: "agility",
    WeaponClass.MEDIUM: "agility",
    WeaponClass.HEAVY: "strength",
}

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

    Prefers the strongest equipped weapon's ``weapon_class`` (#2858) and
    falls back to its ``gear_archetype`` (#2757) when the template hasn't
    been classified. Returns ``None`` when the character has no weapon or
    neither map covers it — the caller then uses the check's default stat.
    """
    from world.combat.services import _select_equipped_weapon  # noqa: PLC0415

    inst = _select_equipped_weapon(character)
    if inst is None:
        return None
    weapon_class = inst.template.weapon_class
    if weapon_class:
        return WEAPON_CLASS_STAT_MAP.get(weapon_class)
    return WEAPON_ARCHETYPE_STAT_MAP.get(inst.template.gear_archetype)
