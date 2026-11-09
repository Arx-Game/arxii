"""Armor soak from worn equipment."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typeclasses.characters import Character
    from world.conditions.models import DamageType
    from world.items.models import ItemInstance


def is_physical(damage_type: DamageType | None) -> bool:
    """Whether a hit of ``damage_type`` is Physical (#5026): untyped damage is (#4742), and
    so is the configured Physical row. With no Physical row configured (an empty database)
    only untyped damage is."""
    if damage_type is None:
        return True
    from world.conditions.services import resolved_damage_type  # noqa: PLC0415

    physical = resolved_damage_type(None)
    return physical is not None and physical.pk == damage_type.pk


def _templates_covering(template_ids: set[int], damage_type: DamageType | None) -> set[int]:
    """Which of ``template_ids`` stand against a hit of ``damage_type`` (#5026): every
    template stops Physical; another type only where the template lists it among the
    types it also protects against. One query, and none for a Physical hit."""
    if is_physical(damage_type) or not template_ids:
        return set(template_ids)
    from world.items.models import ItemTemplate  # noqa: PLC0415

    through = ItemTemplate.also_protects_against.through
    return set(
        through.objects.filter(
            itemtemplate_id__in=template_ids, damagetype_id=damage_type.pk
        ).values_list("itemtemplate_id", flat=True)
    )


def _equipped_armor_soak_pieces(
    character: Character,
    damage_type: DamageType | None = None,
) -> Iterator[tuple[ItemInstance, int]]:
    """Yield (item_instance, soak) for each worn armor piece with positive soak that stands
    against a hit of ``damage_type`` (#5026: ordinary armor stops Physical only; a piece
    whose template lists more types stops those too). None is a Physical hit."""
    from world.items.constants import ARMOR_ARCHETYPES  # noqa: PLC0415

    pieces = [
        (equipped.item_instance, equipped.item_instance.effective_armor_soak)
        for equipped in list(character.equipped_items)
        if equipped.item_instance.template.gear_archetype in ARMOR_ARCHETYPES
    ]
    pieces = [(inst, soak) for inst, soak in pieces if soak > 0]
    covering = _templates_covering({inst.template_id for inst, _ in pieces}, damage_type)
    for inst, soak in pieces:
        if inst.template_id in covering:
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
    damage_type: DamageType | None = None,
) -> tuple[int, int, list[ItemInstance], list[ItemInstance]]:
    """Split worn armor's effective soak into role-compatible vs incompatible buckets (#1174).

    A piece is compatible when ANY engaged PRIMARY covenant role is gear-compatible with
    its archetype through the character's combat style (``StyleGearReach.allows``: clothing
    and other non-armor kinds always fit; armor needs the style to list the kind and the vow).
    With no engaged primary role, all armor is incompatible (it then competes via ``max``
    against a 0 resonant pool → armor-only). PRIMARY-only (#2641, Layer 3 — chassis): a
    secondary vow never widens gear compatibility.

    Only pieces that stand against a hit of ``damage_type`` are split (#5026); None is a
    Physical hit.

    Returns ``(compat_soak, incompat_soak, compat_pieces, incompat_pieces)`` where the
    piece lists are the ItemInstances whose physical soak fell in each bucket (for
    durability wear).
    """
    from world.covenants.style_fit import style_gear_reach  # noqa: PLC0415

    engaged_roles = (
        character.covenant_roles.currently_engaged_primary_roles()
        if hasattr(character, "covenant_roles")
        else []
    )
    pieces = list(_equipped_armor_soak_pieces(character, damage_type))
    # The reach costs queries: build it only when there is armor to test and a vow to test with.
    reach = style_gear_reach(character) if engaged_roles and pieces else None
    compat_soak = incompat_soak = 0
    compat_pieces: list[ItemInstance] = []
    incompat_pieces: list[ItemInstance] = []
    for inst, soak in pieces:
        archetype = inst.template.gear_archetype
        if reach is not None and any(reach.allows(role, archetype) for role in engaged_roles):
            compat_soak += soak
            compat_pieces.append(inst)
        else:
            incompat_soak += soak
            incompat_pieces.append(inst)
    return compat_soak, incompat_soak, compat_pieces, incompat_pieces


def apply_equipped_armor_soak(
    character: Character, damage: int, damage_type: DamageType | None = None
) -> int:
    """Reduce ``damage`` by role-gated equipped-armor soak (#1174, #2533, #4759).

    Armor stands only against the damage types it covers (#5026, owner ruling): every
    piece stops a Physical hit (``damage_type`` None is Physical); a hit of another type
    meets only the pieces whose template lists it in ``also_protects_against``. The
    resonant pool (covenant role, facets, mantles, motif, covenant level) stands against
    every type.

    Worn armor is split by covenant-role compatibility. How much of it counts comes from
    ``defense_style_for`` (#4759): the character's ``CombatStyle`` share scales ALL worn
    armor (a style is how they fight, whatever they wear); with no style, all armor counts
    (legacy, byte-identical). The resonant soak pool (covenant role base +
    facet + mantle + motif + covenant-level, un-blended) then competes with
    *incompatible* armor via ``max``; the (possibly scaled) compatible armor adds on top:

        compat_soak = compat_soak * share / 10        (style)
        incompat_soak = incompat_soak * share / 10    (style)
        soak = compat_soak + max(incompat_soak, resonant)

    Because ``resonant`` scales on character level and physical armor does not, a role
    incompatible with heavy armor sees its resonant protection overtake platemail past
    low levels. Durability wears only on armor whose physical soak contributes to the
    result (all compatible pieces, regardless of the scaled soak's magnitude; incompatible
    pieces only when they win the ``max``).

    Mitigation's weakness (#4759): while a much higher-level NPC's blow resolves against
    a mitigation defender (``world.covenants.defense.mitigation_leak``), part of what the
    armor stopped leaks through. Returns post-soak damage, floored at 0.
    """
    if damage <= 0:
        return damage

    from world.covenants.defense import mitigation_leak  # noqa: PLC0415
    from world.items.services.durability import decrement_item_durability  # noqa: PLC0415

    soak, contributors = _worn_soak(character, damage_type)
    if soak <= 0:
        return damage

    for inst in contributors:
        decrement_item_durability(item_instance=inst)

    soaked = min(soak, damage)
    return damage - soaked + mitigation_leak(character, soaked)


def equipped_armor_soak(character: Character, damage_type: DamageType | None = None) -> int:
    """The soak ``apply_equipped_armor_soak`` would subtract from a hit of ``damage_type``,
    read without wearing any armor (#4892): what a technique's target's soak input reads for
    a duelist."""
    return _worn_soak(character, damage_type)[0]


def _worn_soak(
    character: Character, damage_type: DamageType | None = None
) -> tuple[int, list[ItemInstance]]:
    """The character's soak against one hit and the armor pieces whose soak counts in it.

    The rule ``apply_equipped_armor_soak`` documents: the style share scales the
    armor, the resonant pool competes with incompatible armor, compatible armor adds on top.
    Only armor whose physical soak contributed is listed, for wear.
    """
    from world.covenants.defense import defense_style_for  # noqa: PLC0415

    compat_soak, incompat_soak, compat_pieces, incompat_pieces = _split_armor_soak_by_compatibility(
        character, damage_type
    )
    defense = defense_style_for(character)
    compat_soak = compat_soak * defense.armor_share_tenths // 10
    incompat_soak = incompat_soak * defense.armor_share_tenths // 10
    resonant = _resonant_armor_soak(character)

    incompatible_wins = incompat_soak > 0 and incompat_soak >= resonant
    soak = compat_soak + (incompat_soak if incompatible_wins else resonant)
    contributors = list(compat_pieces)
    if incompatible_wins:
        contributors += incompat_pieces
    return soak, contributors
