"""Equipped weapon selection and profile."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.services.equipment.combat_target_bonus import _combat_target_bonus

if TYPE_CHECKING:
    from typeclasses.characters import Character
    from world.combat.types import WeaponContribution
    from world.conditions.models import DamageType
    from world.items.models import ItemInstance
    from world.magic.models.techniques import AbstractDamageProfile


def _equipped_weapon_archetype(character: Character) -> str | None:
    """The ``gear_archetype`` of character's strongest equipped weapon, or None."""
    inst = _select_equipped_weapon(character)
    if inst is None:
        return None
    return inst.template.gear_archetype


def _select_equipped_weapon(character: Character) -> ItemInstance | None:
    """The character's strongest equipped weapon instance (>0 effective damage).

    Deterministic: max by effective_weapon_damage, tie-break by item_instance pk
    (lowest pk wins, via negating pk in the comparison key).
    """
    from world.items.constants import WEAPON_ARCHETYPES  # noqa: PLC0415

    best = None
    for equipped in character.equipped_items:
        inst = equipped.item_instance
        if inst.template.gear_archetype not in WEAPON_ARCHETYPES:
            continue
        dmg = inst.effective_weapon_damage
        if dmg <= 0:
            continue
        key = (dmg, -inst.pk)
        if best is None or key > best[0]:
            best = (key, inst)
    return best[1] if best is not None else None


def effective_weapon_profile(character: Character) -> WeaponContribution | None:
    """The character's strongest equipped weapon as a combat contribution."""
    from world.combat.types import WeaponContribution  # noqa: PLC0415

    inst = _select_equipped_weapon(character)
    if inst is None:
        return None
    return WeaponContribution(
        damage=inst.effective_weapon_damage,
        damage_type=inst.effective_weapon_damage_type,
    )


def _weapon_augmented_budget(
    profile: AbstractDamageProfile,
    budget: int,
    weapon: WeaponContribution | None,
    sheet: object | None = None,
) -> tuple[int, DamageType | None]:
    """Fold an equipped weapon's contribution into an untyped damage profile's budget.

    For a ``uses_equipped_weapon`` profile with no damage type of its own and an equipped
    weapon, adds the weapon's damage to the formula budget, then the covenant-role
    weapon-damage bonus (``weapon_damage_with_bonus``), and the hit takes the weapon's
    type. A typed weapon profile never turns the weapon's damage into its type (#5026,
    owner ruling): the weapon's part is dealt on its own (``weapon_part_of``), so it passes
    through unchanged here, as do non-weapon profiles and an unarmed attacker.
    Returns ``(budget, damage_type)``.
    """
    profile_damage_type = profile.damage_type
    if profile.uses_equipped_weapon and weapon is not None and profile_damage_type is None:
        budget += weapon_damage_with_bonus(weapon, sheet)
        profile_damage_type = weapon.damage_type
    return budget, profile_damage_type


def weapon_damage_with_bonus(weapon: WeaponContribution, sheet: object | None = None) -> int:
    """The weapon's damage plus the covenant-role weapon-damage bonus when a sheet is given."""
    damage = weapon.damage
    if sheet is not None:
        from world.items.constants import WEAPON_DAMAGE_TARGET_NAME  # noqa: PLC0415

        damage += _combat_target_bonus(sheet, WEAPON_DAMAGE_TARGET_NAME)
    return damage


def splits_weapon_part(profile: AbstractDamageProfile, weapon: WeaponContribution | None) -> bool:
    """Whether ``profile`` deals the equipped weapon's damage as a part of its own (#5026):
    a typed weapon profile with a weapon in hand."""
    return profile.uses_equipped_weapon and weapon is not None and profile.damage_type is not None


def _wear_equipped_weapon(character: Character) -> None:
    """Apply one point of durability wear to the character's strongest weapon.

    Called once per landed weapon-based attack (not once per damage profile), so
    a multi-component technique does not double-wear the weapon.
    """
    weapon_inst = _select_equipped_weapon(character)
    if weapon_inst is None:
        return
    from world.items.services.durability import decrement_item_durability  # noqa: PLC0415

    decrement_item_durability(item_instance=weapon_inst)
