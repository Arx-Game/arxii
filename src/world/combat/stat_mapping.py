"""Weapon→stat mapping for combat checks (#2757).

The calling system determines which stat a combat check rolls from the
equipped weapon's archetype. This is authored content — a simple mapping
from ``GearArchetype`` to stat name. ``None`` means "use the check's
default stat" (no override).

The mapping is intentionally coarse: ``GearArchetype`` distinguishes
one-handed from two-handed, not light/rapier from heavy/warhammer. A
finer weapon-class→stat mapping (keyed on a weapon-class property or
specialization) is a content follow-up. The initial mapping favors
agility for one-handed weapons (the common case: swords, daggers,
rapiers) and strength for two-handed weapons.
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

    Looks up the character's strongest equipped weapon's ``gear_archetype``
    and maps it to a stat name via ``WEAPON_ARCHETYPE_STAT_MAP``. Returns
    ``None`` when the character has no weapon or the archetype isn't in
    the map — the caller then uses the check's default stat.
    """
    from world.combat.services import _equipped_weapon_archetype  # noqa: PLC0415

    archetype = _equipped_weapon_archetype(character)
    if archetype is None:
        return None
    return WEAPON_ARCHETYPE_STAT_MAP.get(archetype)
