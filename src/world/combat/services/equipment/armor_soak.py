"""Armor soak from worn equipment."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typeclasses.characters import Character
    from world.items.models import ItemInstance


def _equipped_armor_soak_pieces(
    character: Character,
) -> Iterator[tuple[ItemInstance, int]]:
    """Yield (item_instance, soak) for each worn armor piece with positive soak."""
    from world.items.constants import ARMOR_ARCHETYPES  # noqa: PLC0415

    for equipped in list(character.equipped_items):
        inst = equipped.item_instance
        if inst.template.gear_archetype in ARMOR_ARCHETYPES:
            soak = inst.effective_armor_soak
            if soak > 0:
                yield inst, soak


def effective_soak_from_armor(character: Character) -> int:
    """Sum effective armor soak across the character's equipped armor pieces."""
    return sum(soak for _, soak in _equipped_armor_soak_pieces(character))


def _resonant_armor_soak(character: Character) -> int:
    """The character's un-blended resonant armor-soak pool (#1174).

    eager CharacterModifier total + equipment_walk_total_unblended for the armor_soak
    target. 0 when the sheet or the seeded target row is absent (combat never hard-depends
    on seed order). This is the pool the incompatible-armor ``max`` competes against.
    """
    from world.items.constants import ARMOR_SOAK_TARGET_NAME  # noqa: PLC0415
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415
    from world.mechanics.services import (  # noqa: PLC0415
        equipment_walk_total_unblended,
        get_modifier_breakdown,
    )

    sheet = character.character_sheet
    if sheet is None:
        return 0
    try:
        target = ModifierTarget.objects.get(name=ARMOR_SOAK_TARGET_NAME)
    except ModifierTarget.DoesNotExist:
        return 0
    eager = get_modifier_breakdown(sheet, target).total
    return eager + equipment_walk_total_unblended(sheet, target)


def _split_armor_soak_by_compatibility(
    character: Character,
) -> tuple[int, int, list[ItemInstance], list[ItemInstance]]:
    """Split worn armor's effective soak into role-compatible vs incompatible buckets (#1174).

    A piece is compatible when ANY engaged PRIMARY covenant role is gear-compatible with
    its archetype (existing GearArchetypeCompatibility). With no engaged primary role,
    all armor is incompatible (it then competes via ``max`` against a 0 resonant pool →
    armor-only). PRIMARY-only (#2641, Layer 3 — chassis): a secondary vow never widens
    gear compatibility.

    Returns ``(compat_soak, incompat_soak, compat_pieces, incompat_pieces)`` where the
    piece lists are the ItemInstances whose physical soak fell in each bucket (for
    durability wear).
    """
    from world.covenants.services import is_gear_compatible  # noqa: PLC0415

    engaged_roles = (
        character.covenant_roles.currently_engaged_primary_roles()
        if hasattr(character, "covenant_roles")
        else []
    )
    compat_soak = incompat_soak = 0
    compat_pieces: list[ItemInstance] = []
    incompat_pieces: list[ItemInstance] = []
    for inst, soak in _equipped_armor_soak_pieces(character):
        archetype = inst.template.gear_archetype
        if any(is_gear_compatible(role, archetype) for role in engaged_roles):
            compat_soak += soak
            compat_pieces.append(inst)
        else:
            incompat_soak += soak
            incompat_pieces.append(inst)
    return compat_soak, incompat_soak, compat_pieces, incompat_pieces


def apply_equipped_armor_soak(character: Character, damage: int) -> int:
    """Reduce ``damage`` by role-gated equipped-armor soak (#1174, #2533).

    Worn armor is split by covenant-role compatibility. Compatible soak is then scaled
    by ``gear_additive_fraction`` (#2533) — the character's engaged defense profile(s)
    dial how much of their COMPATIBLE armor stays additive with their vow's own
    defense; 1 (no profile, or every engaged profile at the default 10 tenths) is the
    legacy fully-additive behavior. The resonant soak pool (covenant role base + facet
    + mantle + motif + covenant-level, un-blended) then competes with *incompatible*
    armor via ``max``; the (possibly scaled) compatible armor adds on top:

        compat_soak = int(compat_soak * gear_additive_fraction(character))
        soak = compat_soak + max(incompat_physical, resonant)

    Because ``resonant`` scales on character level and physical armor does not, a role
    incompatible with heavy armor sees its resonant protection overtake platemail past
    low levels. Durability wears only on armor whose physical soak contributes to the
    result (all compatible pieces, regardless of the scaled soak's magnitude; incompatible
    pieces only when they win the ``max`` — unchanged by the #2533 fraction). Returns
    post-soak damage, floored at 0.
    """
    if damage <= 0:
        return damage

    from world.covenants.services import gear_additive_fraction  # noqa: PLC0415
    from world.items.services.durability import decrement_item_durability  # noqa: PLC0415

    compat_soak, incompat_soak, compat_pieces, incompat_pieces = _split_armor_soak_by_compatibility(
        character
    )
    compat_soak = int(compat_soak * gear_additive_fraction(character))
    resonant = _resonant_armor_soak(character)

    incompatible_wins = incompat_soak >= resonant
    soak = compat_soak + (incompat_soak if incompatible_wins else resonant)
    if soak <= 0:
        return damage

    # Wear only armor whose physical soak actually contributed.
    contributors = list(compat_pieces)
    if incompatible_wins:
        contributors += incompat_pieces
    for inst in contributors:
        decrement_item_durability(item_instance=inst)

    return max(0, damage - soak)
