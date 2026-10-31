"""How a character defends: their combat style, else their vow's defense profile (#4759).

``defense_style_for`` is the one resolver. A character's ``CombatStyle``
(``CharacterSheet.combat_style``) wins; with no style, the highest-tenths engaged
PRIMARY vow's ``CovenantRoleDefenseProfile`` governs, chosen the way
``gear_additive_fraction`` always chose; with neither there is no defense style and
all armor counts, which is the behavior before #4759.

The three defense styles change how an NPC's blow lands on a PC
(``world.combat.services.npc.npc_attack.resolve_npc_attack``):

- **Evasion** defends through the existing dodge path, and usually counts less armor.
- **Barrier**: an absorb ward rolls a check before it absorbs, and the result scales
  how much of the blow it takes (``barrier_absorb_fraction``).
- **Mitigation** (stored ``gear_soak``): armor soaks as normal, but when the attacker's
  level beats the defender's by more than ``MovementConfig.mitigation_level_gap_cap``,
  ``mitigation_leak_percent`` of what the armor stopped leaks through
  (``mitigation_leak``).

The damage pipeline that runs the ward and the armor takes no defense arguments, so the
attack hands its defense down through ``npc_hit_defense`` (a context variable), the way
``dodge_roll_active`` tells the Phase Step ward the roll already answered the hit.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
import contextlib
import contextvars
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any, NamedTuple

from world.covenants.constants import DefenseStyle

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from typeclasses.characters import Character
    from world.checks.models import CheckType
    from world.covenants.models import CovenantRoleDefenseProfile

#: All armor counts: the share with no style and no vow profile (legacy behavior).
FULL_ARMOR_SHARE_TENTHS = 10


class DefenseResolution(NamedTuple):
    """A character's defense style and armor share, and where they came from.

    ``style`` is a ``DefenseStyle`` value, or None when the character has neither a
    combat style nor an engaged vow profile. ``from_combat_style`` is True when the
    character's own ``CombatStyle`` set it: a style's share counts against all worn
    armor, while a vow profile's share keeps its #2533 reach (the vow-compatible armor
    only).
    """

    style: str | None
    armor_share_tenths: int
    from_combat_style: bool


def engaged_primary_defense_profile(character: object) -> CovenantRoleDefenseProfile | None:
    """The engaged PRIMARY vow profile that governs defense, or None (#2533).

    Per engaged (resolved) role: the sub-role's own profile, else its anchor's. The
    profile with the most gear-friendly ``gear_additive_tenths`` wins (the first on a
    tie); gear is physical and counts once. A secondary vow never governs defense
    (#2641).
    """
    from world.covenants.models import CovenantRoleDefenseProfile  # noqa: PLC0415

    if not hasattr(character, "covenant_roles"):
        return None
    engaged_roles = character.covenant_roles.currently_engaged_primary_roles()
    if not engaged_roles:
        return None
    role_pks: set[int] = set()
    for role in engaged_roles:
        role_pks.add(role.pk)
        if role.parent_role_id is not None:
            role_pks.add(role.parent_role_id)
    profiles_by_role_id = {
        profile.covenant_role_id: profile
        for profile in CovenantRoleDefenseProfile.objects.filter(covenant_role_id__in=role_pks)
    }
    best: CovenantRoleDefenseProfile | None = None
    for role in engaged_roles:
        profile = profiles_by_role_id.get(role.pk)
        if profile is None and role.parent_role_id is not None:
            profile = profiles_by_role_id.get(role.parent_role_id)
        if profile is not None and (
            best is None or profile.gear_additive_tenths > best.gear_additive_tenths
        ):
            best = profile
    return best


def defense_style_for(character: object) -> DefenseResolution:
    """How this character defends: combat style, then vow profile, then legacy."""
    sheet = character.character_sheet if hasattr(character, "character_sheet") else None
    style = sheet.combat_style if sheet is not None else None
    if style is not None:
        return DefenseResolution(style.defense_style, style.armor_share_tenths, True)
    profile = engaged_primary_defense_profile(character)
    if profile is not None:
        return DefenseResolution(profile.style, profile.gear_additive_tenths, False)
    return DefenseResolution(None, FULL_ARMOR_SHARE_TENTHS, False)


@dataclass(frozen=True)
class NpcHitDefense:
    """The defense an NPC attack hands down to the ward and the armor it lands on."""

    defender: ObjectDB
    style: str
    attacker_level: int
    defender_level: int
    check_type: CheckType
    target_difficulty: int
    extra_modifiers: int
    perform_check_fn: Callable[..., Any]


#: Set while an NPC blow resolves against a barrier or mitigation defender.
NPC_HIT_DEFENSE: contextvars.ContextVar[NpcHitDefense | None] = contextvars.ContextVar(
    "npc_hit_defense", default=None
)


@contextlib.contextmanager
def npc_hit_defense(defense: NpcHitDefense | None) -> Iterator[None]:
    """Hand ``defense`` to the ward and armor for the enclosed damage (None: no-op)."""
    token = NPC_HIT_DEFENSE.set(defense)
    try:
        yield
    finally:
        NPC_HIT_DEFENSE.reset(token)


def _active_defense(character: Character, style: str) -> NpcHitDefense | None:
    """The NPC hit defense in force for this character with this style, or None."""
    defense = NPC_HIT_DEFENSE.get()
    if defense is None or defense.style != style:
        return None
    if character.pk != defense.defender.pk:  # an interposer's own hit
        return None
    return defense


def barrier_absorb_fraction(character: Character) -> Decimal | None:
    """Roll the barrier's check and return how much of the blow its ward takes.

    None when no barrier NPC hit is resolving against ``character``: the ward then
    absorbs automatically, as it always has. Otherwise the ward rolls the attack's own
    defense check against the attacker's difficulty: a clean defense (no damage on the
    defense ladder) absorbs all of it, a partial one half, anything worse none.
    """
    from world.combat.constants import (  # noqa: PLC0415
        DEFENSE_NO_DAMAGE_THRESHOLD,
        DEFENSE_REDUCED_MULTIPLIER,
        DEFENSE_REDUCED_THRESHOLD,
    )
    from world.combat.stat_mapping import DEFENSE_STAT  # noqa: PLC0415

    defense = _active_defense(character, DefenseStyle.BARRIER)
    if defense is None:
        return None
    result = defense.perform_check_fn(
        defense.defender,
        defense.check_type,
        target_difficulty=defense.target_difficulty,
        extra_modifiers=defense.extra_modifiers,
        stat_override=DEFENSE_STAT,
    )
    if result.success_level >= DEFENSE_NO_DAMAGE_THRESHOLD:
        return Decimal(1)
    if result.success_level >= DEFENSE_REDUCED_THRESHOLD:
        return Decimal(1) - Decimal(str(DEFENSE_REDUCED_MULTIPLIER))
    return Decimal(0)


def mitigation_tuning() -> tuple[int, int]:
    """``(level_gap_cap, leak_percent)`` from MovementConfig, or the field defaults."""
    from world.combat.models import MovementConfig  # noqa: PLC0415

    row = MovementConfig.objects.cached_singleton()
    if row is None:
        row = MovementConfig()  # unsaved: carries every field's default
    return row.mitigation_level_gap_cap, row.mitigation_leak_percent


def mitigation_leak(character: Character, soaked: int) -> int:
    """How much of ``soaked`` leaks through a mitigation defender's armor.

    Zero unless a mitigation NPC hit is resolving against ``character`` and the
    attacker's level beats the defender's by more than the authored cap.
    """
    if soaked <= 0:
        return 0
    defense = _active_defense(character, DefenseStyle.GEAR_SOAK)
    if defense is None:
        return 0
    cap, leak_percent = mitigation_tuning()
    if defense.attacker_level - defense.defender_level <= cap:
        return 0
    return soaked * leak_percent // 100
