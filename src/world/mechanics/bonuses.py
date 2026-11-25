"""The sheet's Bonuses band: every bonus total a character has and what gave it (#5206).

``bonus_groups_for_sheet(sheet)`` lists every bonus the game adds for a target, as
``get_modifier_total`` adds them: the sheet's ``CharacterModifier`` rows valued as
``get_modifier_breakdown`` values them (distinction effects through ``value_held_effects``:
sized effects, amplifiers, immunity, derived amounts; home comfort and achievement rewards as
flat addends; a feature's bonus dropped while clothing covers it), each worn crafted piece,
and the equipment walk (facets, mantles, motif styles, covenant roles and vows). A sized
effect is priced in the lane a roll reads the target in (``ModifierTarget.roll_lane``), so
the band shows the number a roll adds before the lane's taper. Targets staff mark
``spent_at_creation`` are left out, and so are rows whose total is 0 unless they carry
immunity. Groups follow the category's ``display_order``; rows follow the target's
``display_order`` then its name.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from world.checks.modifier_values import ValueTable, load_value_table
from world.mechanics.constants import SOURCE_TYPE_DISTINCTION, SOURCE_TYPE_UNKNOWN
from world.mechanics.derived_amounts import DerivedInputs
from world.mechanics.models import CharacterModifier, ModifierTarget
from world.mechanics.services import (
    _flat_source_contributions,
    _visible_feature_modifiers,
    equipment_walk_target_ids,
    equipment_walk_total,
    held_effect_for,
    modifier_rank_sizes_prefetch,
    sheet_derived_reader,
    sheet_valuation_level,
    value_held_effects,
)
from world.mechanics.terms import term_definition, term_label
from world.mechanics.types import BonusGroup, BonusRow, BonusSource

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet

# The labels the check seam's own breakdown gives these sources
# (``world.checks.services.modifier_target_contributions``), so a player reads one name for
# a source on the sheet and on a roll.
EQUIPMENT_WALK_LABEL = "Equipment & attunement"
CRAFTED_PIECE_LABEL = "Crafted: {piece}"
_TARGET_RELATIONS = (
    "category",
    "target_trait",
    "target_aspect",
    "scope_maneuver_effect",
)


def bonus_groups_for_sheet(sheet: CharacterSheet) -> list[BonusGroup]:
    """The sheet's bonus totals by kind, each with the sources that gave it (#5206).

    One read of the sheet's modifier rows joined to what the valuation and the labels need,
    the equipment walk's candidate targets (``equipment_walk_target_ids``, a bounded number
    of reads gated by the cached handlers) and the worn crafted pieces' targets (the cached
    equipment handler, no read), then one read of the targets only equipment reaches. The
    walk itself runs only on its candidates; a lane's value table loads once, only when a
    sized effect needs it.
    """
    rows = list(
        CharacterModifier.objects.filter(
            character=sheet,
            target__spent_at_creation=False,
            target__is_active=True,
        )
        .select_related(
            *(f"target__{relation}" for relation in _TARGET_RELATIONS),
            "source__distinction_effect__distinction",
            "source__character_distinction__distinction",
            "source__character_distinction__feature_marking",
            "source__character_distinction__feature_trait",
        )
        .prefetch_related(modifier_rank_sizes_prefetch())
    )
    rows = _visible_feature_modifiers(sheet, rows)
    by_target: dict[int, list[CharacterModifier]] = defaultdict(list)
    targets: dict[int, ModifierTarget] = {}
    for row in rows:
        by_target[row.target_id].append(row)
        targets[row.target_id] = row.target

    walk_ids = equipment_walk_target_ids(sheet)
    crafted_ids = _crafted_target_ids(sheet)
    equipment_only = (walk_ids | crafted_ids) - targets.keys()
    if equipment_only:
        targets.update(
            (target.pk, target)
            for target in ModifierTarget.objects.filter(
                pk__in=equipment_only, spent_at_creation=False, is_active=True
            ).select_related(*_TARGET_RELATIONS)
        )

    tables: dict[str, ValueTable] = {}
    derived_inputs = DerivedInputs()
    by_category: dict[int, list[tuple[ModifierTarget, BonusRow]]] = defaultdict(list)
    for target_id, target in targets.items():
        equipment = _equipment_sources(
            sheet, target, walk=target_id in walk_ids, crafted=target_id in crafted_ids
        )
        bonus = _bonus_row(
            sheet, target, by_target.get(target_id, []), equipment, tables, derived_inputs
        )
        if bonus is not None:
            by_category[target.category_id].append((target, bonus))

    groups: list[BonusGroup] = []
    for entries in sorted(
        by_category.values(),
        key=lambda e: (e[0][0].category.display_order, e[0][0].category.name),
    ):
        category = entries[0][0].category
        entries.sort(key=lambda entry: (entry[0].display_order, entry[0].name))
        groups.append(
            BonusGroup(
                category_name=category.name,
                heading=_heading(category.name),
                rows=tuple(bonus for _, bonus in entries),
            )
        )
    return groups


def _heading(category_name: str) -> str:
    """A category's name as a card prints a term, first letter capitalized:
    ``roll_modifier`` -> ``Roll modifier``."""
    label = term_label(category_name)
    return label[:1].upper() + label[1:]


def _bonus_row(  # noqa: PLR0913 - one target's rows, its equipment, and the read's caches
    sheet: CharacterSheet,
    target: ModifierTarget,
    rows: list[CharacterModifier],
    equipment: list[BonusSource],
    tables: dict[str, ValueTable],
    derived_inputs: DerivedInputs,
) -> BonusRow | None:
    """One target's row, its sources added as ``get_modifier_total`` adds them; None when
    the row adds nothing and grants no immunity.

    ``equipment`` is the worn crafted pieces' and the equipment walk's shares
    (``_equipment_sources``). Immunity blocks only the modifier rows' negatives, as in
    ``get_modifier_total``.
    """
    distinction_rows = [row for row in rows if row.source.distinction_effect is not None]
    other_rows = [
        row
        for row in rows
        if row.source.source_type not in (SOURCE_TYPE_DISTINCTION, SOURCE_TYPE_UNKNOWN)
    ]
    value_table = _value_table(target, distinction_rows, tables)
    valuation = value_held_effects(
        [held_effect_for(row) for row in distinction_rows],
        level=sheet_valuation_level(sheet, value_table),
        value_table=value_table,
        derived_reader=sheet_derived_reader(sheet, derived_inputs),
    )
    flat_details, flat_total, _ = _flat_source_contributions(other_rows, valuation.has_immunity)
    total = valuation.total + flat_total + sum(source.value for source in equipment)
    if total == 0 and not valuation.has_immunity:
        return None
    sources = [
        BonusSource(label=_card_label(row), value=detail.final_value)
        for row, detail in zip(distinction_rows, valuation.sources, strict=True)
        if not detail.blocked_by_immunity
    ]
    sources.extend(
        BonusSource(label=detail.source_name, value=detail.final_value)
        for detail in flat_details
        if not detail.blocked_by_immunity
    )
    sources.extend(equipment)
    return BonusRow(
        target_name=target.name,
        label=term_label(target.name),
        definition=term_definition(target),
        total=total,
        sources=tuple(sources),
        immune=valuation.has_immunity,
    )


def _value_table(
    target: ModifierTarget,
    distinction_rows: list[CharacterModifier],
    tables: dict[str, ValueTable],
) -> ValueTable | None:
    """The table of the lane a roll reads the target in (``ModifierTarget.roll_lane``) when
    a sized effect needs it, loaded once per lane."""
    lane = target.roll_lane
    if lane is None or not any(
        row.source.distinction_effect.modifier_size is not None for row in distinction_rows
    ):
        return None
    if lane not in tables:
        tables[lane] = load_value_table(lane)
    return tables[lane]


def _crafted_target_ids(sheet: CharacterSheet) -> set[int]:
    """The targets a worn crafted piece names, from the cached equipment handler."""
    character = sheet.character
    if character is None:
        return set()
    try:
        return character.equipped_items.crafted_modifier_target_ids()
    except AttributeError:
        # A raw ObjectDB fixture carries no equipment handler, so nothing is worn.
        return set()


def _equipment_sources(
    sheet: CharacterSheet, target: ModifierTarget, *, walk: bool, crafted: bool
) -> list[BonusSource]:
    """Each worn crafted piece's share, then the equipment walk's, as the roll names them.

    ``walk`` and ``crafted`` say whether the target is one the walk or a worn crafted piece
    can reach, so neither runs on a target it cannot touch.

    Read through the functions ``get_modifier_total`` adds them with: the equipment
    handler's ``crafted_modifier_by_piece`` (whose sum is ``crafted_modifier_total``) and
    ``equipment_walk_total``.
    """
    sources: list[BonusSource] = []
    if crafted:
        sources.extend(
            BonusSource(label=CRAFTED_PIECE_LABEL.format(piece=piece.display_name), value=value)
            for piece, value in sheet.character.equipped_items.crafted_modifier_by_piece(target)
        )
    if walk:
        value = equipment_walk_total(sheet, target)
        if value:
            sources.append(BonusSource(label=EQUIPMENT_WALK_LABEL, value=value))
    return sources


def _card_label(row: CharacterModifier) -> str:
    """A card source by its distinction's name, with the feature a per-feature card is held
    on and its rank when the rank is above 1: ``Alluring on hair color (Rank 2)``."""
    name = row.source.distinction_effect.distinction.name
    held = row.source.character_distinction
    if held is None:
        return name
    feature = ""
    if held.feature_trait_id is not None:
        feature = held.feature_trait.display_name
    elif held.feature_marking_id is not None:
        feature = held.feature_marking.name
    if feature:
        name = f"{name} on {feature.lower()}"
    if held.rank > 1:
        name = f"{name} (Rank {held.rank})"
    return name
