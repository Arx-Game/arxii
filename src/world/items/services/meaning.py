"""What an item means to the character holding it (#4500, #4462).

One reader answers the question for every use: a sacrifice at a shrine, a ceremony
offering, and later a worn piece and the GM's detail view. It computes the item's
meaning points from records the game already keeps and **never reads a price**: not
the template's value, a fee, a sale price or the materials spent. A bought item with no
history has no meaning however much it cost.

Signals (6a): carried, gift, heirloom, own work, made by a tie. The personal ones count
only after the carry gate (``DevotionConfig.sacrifice_min_carried_days``) and carried
itself counts only alongside another signal, so holding a bought item is never meaning.
When one person is both the maker and the giver, their tie counts once, in made by a tie,
and the gift adds a flat 1 for the further act.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils import timezone

from world.items.constants import MeaningSignalKind, OwnershipEventType
from world.items.types import ItemMeaning, MeaningSignal

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance
    from world.scenes.models import Persona
    from world.worship.models import DevotionConfig

#: Most INHERITED holding events that count toward the heirloom signal.
HEIRLOOM_MAX_POINTS = 3
#: Points the gift signal gives before the giver's claimed tier is added.
GIFT_BASE_POINTS = 1


def _persona_name(sheet: CharacterSheet) -> str:
    persona = sheet.primary_persona
    return persona.name if persona is not None else str(sheet)


def _carried_days(item: ItemInstance) -> int:
    return (timezone.now() - item.held_since).days


def _makers(item: ItemInstance, holder: CharacterSheet) -> list[CharacterSheet]:
    """Everyone who made the item for a holder: its crafter, and the seller of each
    crafting-service sale on it. Never the holder."""
    from world.items.market.models import MarketSale  # noqa: PLC0415

    found: dict[int, CharacterSheet] = {}
    if item.crafter_character_sheet_id is not None:
        found[item.crafter_character_sheet_id] = item.crafter_character_sheet
    sales = item.market_sales.filter(kind=MarketSale.SaleKind.SERVICE).select_related(
        "seller_persona__character_sheet"
    )
    for sale in sales:
        seller: Persona | None = sale.seller_persona
        if seller is not None:
            found.setdefault(seller.character_sheet_id, seller.character_sheet)
    found.pop(holder.pk, None)
    return list(found.values())


def _made_by_tie(
    item: ItemInstance, holder: CharacterSheet, config: DevotionConfig
) -> tuple[MeaningSignal | None, int | None]:
    """The made-by-a-tie signal for the best maker, and that maker's sheet pk."""
    from world.relationships.helpers import pair_tier  # noqa: PLC0415

    best: tuple[int, CharacterSheet] | None = None
    for maker in _makers(item, holder):
        tier = pair_tier(holder, maker)
        if tier > 0 and (best is None or tier > best[0]):
            best = (tier, maker)
    if best is None:
        return None, None
    tier, maker = best
    points = min(tier, config.maker_tie_max_points)
    signal = MeaningSignal(
        MeaningSignalKind.MADE_BY_TIE, points, f"{_persona_name(maker)}, pair tier {tier}"
    )
    return signal, maker.pk


def _gift(
    item: ItemInstance, holder: CharacterSheet, tie_counted_for: int | None
) -> MeaningSignal | None:
    """The gift signal: 1 plus the holder's claimed tier toward the giver. When the giver
    is the maker whose tie already counted, only the flat 1 for the further act."""
    from world.relationships.models import CharacterRelationship  # noqa: PLC0415

    event = item.holding_event
    if event is None or event.event_type != OwnershipEventType.GIVEN:
        return None
    giver = event.from_character_sheet
    if giver is None or giver.pk == holder.pk:
        return None
    if tie_counted_for == giver.pk:
        return MeaningSignal(
            MeaningSignalKind.GIFT,
            GIFT_BASE_POINTS,
            f"from {_persona_name(giver)}, whose tie already counted",
        )
    side = CharacterRelationship.objects.filter(source=holder, target=giver).first()
    tier = side.tier if side is not None else 0
    return MeaningSignal(
        MeaningSignalKind.GIFT,
        GIFT_BASE_POINTS + tier,
        f"from {_persona_name(giver)}; tie tier {tier}",
    )


def _heirloom(item: ItemInstance) -> MeaningSignal | None:
    inherited = item.ownership_events.filter(event_type=OwnershipEventType.INHERITED).count()
    if inherited == 0:
        return None
    return MeaningSignal(
        MeaningSignalKind.HEIRLOOM,
        min(inherited, HEIRLOOM_MAX_POINTS),
        f"inherited {inherited} time{'s' if inherited != 1 else ''}",
    )


def _carried(days: int, config: DevotionConfig) -> MeaningSignal | None:
    if days < config.sacrifice_min_carried_days:
        return None
    extra = (days - config.sacrifice_min_carried_days) // max(
        config.sacrifice_carried_days_per_point, 1
    )
    points = min(1 + extra, config.sacrifice_carried_max_points)
    if points <= 0:
        return None
    return MeaningSignal(MeaningSignalKind.CARRIED, points, f"held {days} days")


def item_meaning(
    item: ItemInstance, holder: CharacterSheet, *, config: DevotionConfig
) -> ItemMeaning:
    """The signals that make ``item`` matter to ``holder``, and so its meaning points.

    Pure of side effects. An item with no signal has no meaning, however it was paid for.
    ``config`` is the devotion config (the numbers are staff-tuned there); it is passed in
    so the items app does not import worship.
    """
    days = _carried_days(item)
    if days < config.sacrifice_min_carried_days:
        return ItemMeaning()
    signals: list[MeaningSignal] = []
    made_signal, maker_pk = _made_by_tie(item, holder, config)
    if made_signal is not None:
        signals.append(made_signal)
    gift = _gift(item, holder, maker_pk)
    if gift is not None:
        signals.append(gift)
    heirloom = _heirloom(item)
    if heirloom is not None:
        signals.append(heirloom)
    if item.crafter_character_sheet_id == holder.pk:
        signals.append(MeaningSignal(MeaningSignalKind.OWN_WORK, 1, "made by the holder"))
    if not signals:
        return ItemMeaning()
    carried = _carried(days, config)
    if carried is not None:
        signals.insert(0, carried)
    return ItemMeaning(tuple(signals))
