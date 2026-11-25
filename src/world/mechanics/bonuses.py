"""The sheet's Bonuses band: every bonus total a character has and what gave it (#5206).

``bonus_groups(...)`` is the one place the band is grouped, labelled, valued and filtered.
It takes the held cards and the flat addends per target and asks a callback for each
target's equipment shares, so only the source of what is held differs between callers:

* ``bonus_groups_for_sheet(sheet, *, privileged)`` reads a character's ``CharacterModifier``
  rows, valued as ``get_modifier_breakdown`` values them (distinction effects through
  ``value_held_effects``: sized effects, amplifiers, immunity, derived amounts; home comfort
  and achievement rewards as flat addends; a feature's bonus dropped while clothing covers
  it), each worn crafted piece, and the equipment walk (facets, mantles, motif styles,
  covenant roles and vows).
* ``world.character_creation.sheet_preview`` builds the same input from a draft's cards and
  its home's comfort, so a waiting sheet and the character approval makes list equal groups.

A sized effect is priced in the lane a roll reads the target in (``ModifierTarget.roll_lane``),
so the band shows the number a roll adds before the lane's taper. Targets staff mark
``spent_at_creation`` are left out, and so are inactive targets and rows whose total is 0
unless they carry immunity. Groups follow the category's ``display_order``; rows follow the
target's ``display_order`` then its name.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING

from world.checks.modifier_values import ValueTable, load_value_table
from world.distinctions.types import held_distinction_sort_key
from world.mechanics.constants import SOURCE_TYPE_DISTINCTION, SOURCE_TYPE_UNKNOWN
from world.mechanics.derived_amounts import DerivedInputs
from world.mechanics.models import CharacterModifier, ModifierTarget
from world.mechanics.services import (
    DerivedAmountReader,
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
from world.mechanics.types import BonusGroup, BonusRow, BonusSource, HeldCardBonus

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet

# The labels the check seam's own breakdown gives these sources
# (``world.checks.services.modifier_target_contributions``), so a player reads one name for
# a source on the sheet and on a roll.
EQUIPMENT_WALK_LABEL = "Equipment & attunement"
CRAFTED_PIECE_LABEL = "Crafted: {piece}"
#: The relations a target needs selected so labelling and the lane read run no query.
TARGET_RELATIONS = (
    "category",
    "target_trait",
    "target_aspect",
    "scope_maneuver_effect",
)

LevelForTable = Callable[[ValueTable | None], int | None]
EquipmentSources = Callable[[ModifierTarget], list[BonusSource]]


def bonus_groups(  # noqa: PLR0913 - what is held, per target, and how to value it
    targets: Mapping[int, ModifierTarget],
    *,
    cards: Mapping[int, Sequence[HeldCardBonus]],
    flats: Mapping[int, Sequence[BonusSource]],
    equipment: EquipmentSources,
    level_for: LevelForTable,
    derived_reader: DerivedAmountReader,
    privileged: bool = True,
) -> list[BonusGroup]:
    """Every bonus total by kind, each with the sources that gave it (#5206).

    ``privileged`` is the viewer's: the owner or staff read every source line, anyone else
    reads no line for a secret card (``HeldCardBonus.secret``), whose value still counts in
    the total, as the buffed statistic counts it.

    ``targets`` maps a target's pk to the target (its ``TARGET_RELATIONS`` selected);
    ``cards`` and ``flats`` map a target's pk to what is held on it, in the order a roll
    reads it. ``equipment`` gives a target's equipment shares, ``level_for`` the level a
    sized effect reads a lane's table at, and ``derived_reader`` a derived amount. A lane's
    value table loads once, only when a sized effect needs it.
    """
    tables: dict[str, ValueTable] = {}
    by_category: dict[int, list[tuple[ModifierTarget, BonusRow]]] = defaultdict(list)
    for target_id, target in targets.items():
        if target.spent_at_creation or not target.is_active:
            continue
        bonus = _bonus_row(
            target,
            cards.get(target_id, ()),
            flats.get(target_id, ()),
            equipment(target),
            level_for=level_for,
            derived_reader=derived_reader,
            tables=tables,
            privileged=privileged,
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


def bonus_groups_for_sheet(sheet: CharacterSheet, *, privileged: bool) -> list[BonusGroup]:
    """The sheet's bonus totals by kind, each with the sources that gave it (#5206).

    ``privileged`` (the owner or staff) decides whether a secret card's source line shows.

    One read of the sheet's modifier rows joined to what the valuation and the labels need,
    the equipment walk's candidate targets (``equipment_walk_target_ids``, a bounded number
    of reads gated by the cached handlers) and the worn crafted pieces' targets (the cached
    equipment handler, no read), then one read of the targets only equipment reaches. The
    walk itself runs only on its candidates.
    """
    rows = list(
        CharacterModifier.objects.filter(
            character=sheet,
            target__spent_at_creation=False,
            target__is_active=True,
        )
        .select_related(
            *(f"target__{relation}" for relation in TARGET_RELATIONS),
            "source__distinction_effect__distinction",
            "source__character_distinction__distinction",
            "source__character_distinction__feature_marking",
            "source__character_distinction__feature_trait",
        )
        .prefetch_related(modifier_rank_sizes_prefetch())
    )
    rows = _visible_feature_modifiers(sheet, rows)
    cards: dict[int, list[HeldCardBonus]] = defaultdict(list)
    flats: dict[int, list[BonusSource]] = defaultdict(list)
    targets: dict[int, ModifierTarget] = {}
    for row in rows:
        targets[row.target_id] = row.target
        if row.source.distinction_effect is not None:
            held = row.source.character_distinction
            cards[row.target_id].append(
                HeldCardBonus(
                    label=_row_card_label(row),
                    held=held_effect_for(row),
                    secret=held is not None and held.is_secret,
                )
            )
        elif row.source.source_type not in (SOURCE_TYPE_DISTINCTION, SOURCE_TYPE_UNKNOWN):
            flats[row.target_id].append(
                BonusSource(label=row.source.source_display, value=row.value)
            )

    walk_ids = equipment_walk_target_ids(sheet)
    crafted_ids = _crafted_target_ids(sheet)
    equipment_only = (walk_ids | crafted_ids) - targets.keys()
    if equipment_only:
        targets.update(
            (target.pk, target)
            for target in ModifierTarget.objects.filter(
                pk__in=equipment_only, spent_at_creation=False, is_active=True
            ).select_related(*TARGET_RELATIONS)
        )

    def equipment(target: ModifierTarget) -> list[BonusSource]:
        return _equipment_sources(
            sheet, target, walk=target.pk in walk_ids, crafted=target.pk in crafted_ids
        )

    return bonus_groups(
        targets,
        cards=cards,
        flats=flats,
        equipment=equipment,
        level_for=lambda table: sheet_valuation_level(sheet, table),
        derived_reader=sheet_derived_reader(sheet, DerivedInputs()),
        privileged=privileged,
    )


def _heading(category_name: str) -> str:
    """A category's name as a card prints a term, first letter capitalized:
    ``roll_modifier`` -> ``Roll modifier``."""
    label = term_label(category_name)
    return label[:1].upper() + label[1:]


def _bonus_row(  # noqa: PLR0913 - one target's holdings, its equipment, and the read's caches
    target: ModifierTarget,
    cards: Sequence[HeldCardBonus],
    flats: Sequence[BonusSource],
    equipment: list[BonusSource],
    *,
    level_for: LevelForTable,
    derived_reader: DerivedAmountReader,
    tables: dict[str, ValueTable],
    privileged: bool,
) -> BonusRow | None:
    """One target's row and its sources; None when the row adds nothing and grants no
    immunity.

    The sources are the ones ``get_modifier_total`` sums, but a sized effect is valued the
    way the check seam values it, in the target's roll lane (``ModifierTarget.roll_lane``)
    at the holder's level, where ``get_modifier_total`` keeps the stored flat value; the
    lane's taper is not applied. ``equipment`` is the worn crafted pieces' and the
    equipment walk's shares. Immunity blocks only the cards' and the flat addends'
    negatives, as in ``get_modifier_breakdown``.
    """
    # A row's card sources read in the sheet's card order (``held_distinction_sort_key``),
    # whatever order the rows or the draft's picks came in; the valuation is order-free.
    cards = sorted(
        cards,
        key=lambda card: held_distinction_sort_key(card.held.effect.distinction.name, card.label),
    )
    value_table = _value_table(target, cards, tables)
    valuation = value_held_effects(
        [card.held for card in cards],
        level=level_for(value_table),
        value_table=value_table,
        derived_reader=derived_reader,
    )
    flat_shown = [flat for flat in flats if not (valuation.has_immunity and flat.value < 0)]
    total = (
        valuation.total
        + sum(flat.value for flat in flat_shown)
        + sum(source.value for source in equipment)
    )
    if total == 0 and not valuation.has_immunity:
        return None
    sources = [
        BonusSource(label=card.label, value=detail.final_value)
        for card, detail in zip(cards, valuation.sources, strict=True)
        if not detail.blocked_by_immunity and (privileged or not card.secret)
    ]
    sources.extend(flat_shown)
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
    cards: Sequence[HeldCardBonus],
    tables: dict[str, ValueTable],
) -> ValueTable | None:
    """The table of the lane a roll reads the target in (``ModifierTarget.roll_lane``) when
    a sized effect needs it, loaded once per lane."""
    lane = target.roll_lane
    if lane is None or not any(card.held.effect.modifier_size is not None for card in cards):
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


def card_label(name: str, *, feature: str = "", rank: int = 1) -> str:
    """A card source by its distinction's name, with the feature a per-feature card is held
    on and its rank when the rank is above 1: ``Alluring on hair color (Rank 2)``.

    ``feature`` is the trait's display name or the marking's name, blank for a plain card.
    The sheet names its rows this way and a character-creation draft names its cards the
    same way.
    """
    if feature:
        name = f"{name} on {feature.lower()}"
    if rank > 1:
        name = f"{name} (Rank {rank})"
    return name


def _row_card_label(row: CharacterModifier) -> str:
    """A card row's label (``card_label``) from its held distinction."""
    name = row.source.distinction_effect.distinction.name
    held = row.source.character_distinction
    if held is None:
        return name
    feature = ""
    if held.feature_trait_id is not None:
        feature = held.feature_trait.display_name
    elif held.feature_marking_id is not None:
        feature = held.feature_marking.name
    return card_label(name, feature=feature, rank=held.rank)
