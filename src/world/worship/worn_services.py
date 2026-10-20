"""What she wears counts with her gods (#4520, #4462 section 6.4; folds #4333 slice 8).

When a character invokes a being, the game reads the pieces she has on that carry at
least one facet the being favors (``BeingFacet``). Each piece's meaning points
(``world.items.services.meaning.item_meaning``, which reads records and never a price) are
capped at ``DevotionConfig.worn_item_max_points`` and multiplied by that facet's
``invocation_ease_points``; the same points times ``earning_bonus_percent`` raise the
earning rate. At most ``worn_items_counted`` pieces count, highest meaning first, and the
ease of all of them together is capped at ``invocation_meaning_ease_max``. A piece with no
meaning adds nothing, so a bought piece with no other history never counts however many
favored facets it carries.

The ease is added to ``invocation_difficulty`` as one more labelled ease, lowering the
difficulty the invocation check rolls against. It is not also passed to the check as a
``ModifierContribution``: that would count the same piece twice, once in the displayed
difficulty and once in the roll.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.items.services.meaning import item_meaning
from world.worship.types import WornMeaning, WornPiece

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance
    from world.worship.models import (
        BeingFacet,
        FavorInvocation,
        InvocationPiece,
        WorshippedBeing,
    )


def _favored_pieces(
    sheet: CharacterSheet, favored: dict[int, BeingFacet]
) -> dict[int, tuple[ItemInstance, BeingFacet]]:
    """Each worn item carrying a favored facet, with the facet that eases it most.

    A multi-slot piece appears once. Only facets still on the item count: the equipment
    handler's facet cache holds attached rows only.
    """
    found: dict[int, tuple[ItemInstance, BeingFacet]] = {}
    for equipped in sheet.character.equipped_items:
        item = equipped.item_instance
        if item.pk in found:
            continue
        matches = [favored[f.facet_id] for f in item.cached_item_facets if f.facet_id in favored]
        if matches:
            best = max(
                matches,
                key=lambda bf: (bf.invocation_ease_points, bf.earning_bonus_percent, -bf.pk),
            )
            found[item.pk] = (item, best)
    return found


def worn_meaning(sheet: CharacterSheet, being: WorshippedBeing) -> WornMeaning:
    """The worn pieces that count with ``being`` for ``sheet``, and what they add."""
    from world.worship.invocation_services import get_devotion_config  # noqa: PLC0415

    config = get_devotion_config()
    favored = {row.facet_id: row for row in being.being_facets.select_related("facet")}
    empty = WornMeaning(
        ease_cap=config.invocation_meaning_ease_max, items_counted_max=config.worn_items_counted
    )
    if not favored:
        return empty
    read = []
    for item, row in _favored_pieces(sheet, favored).values():
        meaning = item_meaning(item, sheet, config=config, being=being)
        points = min(meaning.points, config.worn_item_max_points)
        read.append((points * row.invocation_ease_points, points, item, row, meaning))
    if not read:
        return empty
    read.sort(key=lambda entry: (-entry[1], -entry[0], entry[2].pk))
    pieces: list[WornPiece] = []
    counted = 0
    for _ease, points, item, row, meaning in read:
        counts = points > 0 and counted < config.worn_items_counted
        counted += 1 if counts else 0
        pieces.append(
            WornPiece(
                item=item,
                item_name=str(item),
                facet_name=row.facet.name,
                meaning=meaning,
                points=points,
                ease_per_point=row.invocation_ease_points,
                earning_bonus_percent=row.earning_bonus_percent,
                counted=counts,
            )
        )
    return WornMeaning(
        pieces=tuple(pieces),
        ease_cap=config.invocation_meaning_ease_max,
        items_counted_max=config.worn_items_counted,
    )


def record_invocation_pieces(
    invocation: FavorInvocation, worn: WornMeaning
) -> list[InvocationPiece]:
    """Snapshot the pieces that counted onto the invocation, for the GM's detail."""
    from world.worship.models import InvocationPiece, InvocationPieceSignal  # noqa: PLC0415

    rows: list[InvocationPiece] = []
    for piece in worn.counted:
        row = InvocationPiece.objects.create(
            invocation=invocation,
            item_name=piece.item_name,
            facet_name=piece.facet_name,
            points=piece.points,
            ease_per_point=piece.ease_per_point,
        )
        InvocationPieceSignal.objects.bulk_create(
            InvocationPieceSignal(piece=row, kind=s.kind, points=s.points, detail=s.detail)
            for s in piece.meaning.signals
        )
        rows.append(row)
    return rows
