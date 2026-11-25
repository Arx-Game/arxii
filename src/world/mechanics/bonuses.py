"""The sheet's Bonuses band: every bonus total a character has and what gave it (#5206).

``bonus_groups_for_sheet(sheet)`` reads the sheet's ``CharacterModifier`` rows once and
values each target the way a roll's ``get_modifier_breakdown`` does: distinction effects
through ``value_held_effects`` (sized effects, amplifiers, immunity, derived amounts),
home comfort and achievement rewards as flat addends, a feature's bonus dropped while
clothing covers it. Targets staff mark ``spent_at_creation`` are left out, and so are rows
whose total is 0 unless they carry immunity. Groups follow the category's
``display_order``; rows follow the target's ``display_order`` then its name.
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


def bonus_groups_for_sheet(sheet: CharacterSheet) -> list[BonusGroup]:
    """The sheet's bonus totals by kind, each with the sources that gave it (#5206).

    One bounded read of the sheet's modifier rows, joined to what the valuation and the
    labels need; a lane's value table loads once, only when a sized effect needs it.
    """
    rows = list(
        CharacterModifier.objects.filter(
            character=sheet,
            target__spent_at_creation=False,
            target__is_active=True,
        )
        .select_related(
            "target__category",
            "target__target_trait",
            "target__target_aspect",
            "target__scope_maneuver_effect",
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

    tables: dict[str, ValueTable] = {}
    derived_inputs = DerivedInputs()
    by_category: dict[int, list[tuple[ModifierTarget, BonusRow]]] = defaultdict(list)
    for target_id, target_rows in by_target.items():
        target = targets[target_id]
        bonus = _bonus_row(sheet, target, target_rows, tables, derived_inputs)
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


def _bonus_row(
    sheet: CharacterSheet,
    target: ModifierTarget,
    rows: list[CharacterModifier],
    tables: dict[str, ValueTable],
    derived_inputs: DerivedInputs,
) -> BonusRow | None:
    """One target's row, valued as ``get_modifier_breakdown`` values it; None when the row
    adds nothing and grants no immunity."""
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
    total = valuation.total + flat_total
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
    """The target's lane table when a sized effect needs it, loaded once per lane."""
    lane = target.value_lane
    if lane is None or not any(
        row.source.distinction_effect.modifier_size is not None for row in distinction_rows
    ):
        return None
    if lane not in tables:
        tables[lane] = load_value_table(lane)
    return tables[lane]


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
