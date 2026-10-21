"""What an item means to the character holding it (#4500, #4462).

One reader answers the question for every use: a sacrifice at a shrine, a ceremony
offering, and later a worn piece and the GM's detail view. It computes the item's
meaning points from records the game already keeps and **never reads a price**: not
the template's value, a fee, a sale price or the materials spent. A bought item with no
history has no meaning however much it cost.

Signals: carried, gift, heirloom, own work, made by a tie, the commission loop's
designed by you, made for, made from and shown (#4512), resonance fed (#4520), and trophy
and keepsake with its match (#4530). The personal ones count only after the carry gate
(``DevotionConfig.sacrifice_min_carried_days``); shown and trophy are earned in play and have
no gate; a keepsake waits ``keepsake_wait_days`` from its declaration instead. Carried itself
counts only alongside another signal, so holding a bought item is never meaning. A
requested item's points are request-specific (they depend on the open pledge or the rite),
so the caller adds that signal; matching a request is the one place an item's value is read,
and only as a ceiling that keeps the request cheap. When one person is the maker, the
dedicator and the giver, their tie counts once, in the first of made by a tie, gift and made
for that applies, and each further act adds a flat 1 (owner ruling, 2026-10-18).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from django.db.models import Q
from django.utils import timezone

from world.items.constants import KeepsakeSubject, MeaningSignalKind, OwnershipEventType
from world.items.types import ItemMeaning, MeaningSignal

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance, Keepsake
    from world.scenes.models import Persona
    from world.worship.models import DevotionConfig, WorshippedBeing

#: Most INHERITED holding events that count toward the heirloom signal.
HEIRLOOM_MAX_POINTS = 3
#: Points the gift signal gives before the giver's claimed tier is added.
GIFT_BASE_POINTS = 1
#: Points a keepsake gives before its subject's scale is added (#4530).
KEEPSAKE_BASE_POINTS = 1
#: Points on top of a keepsake whose subject is the being the reading is for (#4530).
KEEPSAKE_BEING_MATCH_POINTS = 2


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
    item: ItemInstance, holder: CharacterSheet, tie_counted_for: set[int]
) -> MeaningSignal | None:
    """The gift signal: 1 plus the holder's claimed tier toward the giver. When the giver
    is someone whose tie already counted, only the flat 1 for the further act.
    ``tie_counted_for`` gains the giver when their tie counts here."""
    from world.relationships.models import CharacterRelationship  # noqa: PLC0415

    event = item.holding_event
    if event is None or event.event_type != OwnershipEventType.GIVEN:
        return None
    giver = event.from_character_sheet
    if giver is None or giver.pk == holder.pk:
        return None
    if giver.pk in tie_counted_for:
        return MeaningSignal(
            MeaningSignalKind.GIFT,
            GIFT_BASE_POINTS,
            f"from {_persona_name(giver)}, whose tie already counted",
        )
    side = CharacterRelationship.objects.filter(source=holder, target=giver).first()
    tier = side.tier if side is not None else 0
    tie_counted_for.add(giver.pk)
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


def _designed(item: ItemInstance, holder: CharacterSheet) -> MeaningSignal | None:
    """Designed by you: 1 when the holder wrote the item's name or description. The
    designer is stamped only when text is written, so the fee counts for nothing."""
    if item.designer_character_sheet_id != holder.pk:
        return None
    return MeaningSignal(MeaningSignalKind.DESIGNED, 1, "wrote its name or description")


def _bought_from(item: ItemInstance, holder: CharacterSheet, seller: CharacterSheet) -> bool:
    """Whether the holder bought the item from ``seller`` (a ware sale)."""
    from world.items.market.models import MarketSale  # noqa: PLC0415

    return item.market_sales.filter(
        kind=MarketSale.SaleKind.WARE,
        buyer_persona__character_sheet=holder,
        seller_persona__character_sheet=seller,
    ).exists()


def _made_for(
    item: ItemInstance,
    holder: CharacterSheet,
    tie_counted_for: set[int],
    config: DevotionConfig,
) -> MeaningSignal | None:
    """Made for: 1 plus the holder's claimed tier toward whoever dedicated the piece, up
    to ``made_for_max_points``; 0 when the holder bought it from the dedicator, and
    nothing unless the holder is the dedicatee. A dedicator whose tie already counted
    (as the maker or the giver) adds a flat 1 for the further act."""
    from world.relationships.models import CharacterRelationship  # noqa: PLC0415

    to_persona, by_persona = item.dedicated_to_persona, item.dedicated_by_persona
    if to_persona is None or by_persona is None:
        return None
    if to_persona.character_sheet_id != holder.pk:
        return None
    dedicator = by_persona.character_sheet
    if dedicator.pk == holder.pk or _bought_from(item, holder, dedicator):
        return None
    name = _persona_name(dedicator)
    if dedicator.pk in tie_counted_for:
        return MeaningSignal(
            MeaningSignalKind.MADE_FOR,
            min(GIFT_BASE_POINTS, config.made_for_max_points),
            f"dedicated by {name}, whose tie already counted",
        )
    side = CharacterRelationship.objects.filter(source=holder, target=dedicator).first()
    tier = side.tier if side is not None else 0
    tie_counted_for.add(dedicator.pk)
    return MeaningSignal(
        MeaningSignalKind.MADE_FOR,
        min(GIFT_BASE_POINTS + tier, config.made_for_max_points),
        f"dedicated by {name}; tie tier {tier}",
    )


def _made_from(
    item: ItemInstance, holder: CharacterSheet, config: DevotionConfig
) -> MeaningSignal | None:
    """Made from: what the worked-in item meant to the crafter when it was used up, up to
    ``made_from_max_points``. Counts for the crafter and for whoever the piece was made
    for; a piece passed on keeps the record for examine but not the points."""
    to_persona = item.dedicated_to_persona
    is_dedicatee = to_persona is not None and to_persona.character_sheet_id == holder.pk
    if item.crafter_character_sheet_id != holder.pk and not is_dedicatee:
        return None
    rows = list(item.lineage.all())
    recorded = sum(row.points for row in rows)
    if recorded <= 0:
        return None
    points = min(recorded, config.made_from_max_points)
    names = ", ".join(row.source_name for row in rows)
    capped = f" (cap {config.made_from_max_points})" if points < recorded else ""
    return MeaningSignal(
        MeaningSignalKind.MADE_FROM, points, f"{names}, {recorded} recorded{capped}"
    )


def _shown_cutoff(weeks: int) -> datetime | None:
    """When the shown window opens: the start of the game week ``weeks`` back, counting the
    current one. None when the clock has fewer weeks than that (everything counts)."""
    from world.game_clock.models import GameWeek  # noqa: PLC0415

    starts = list(
        GameWeek.objects.order_by("-started_at").values_list("started_at", flat=True)[:weeks]
    )
    return starts[-1] if len(starts) >= weeks else None


def _shown(item: ItemInstance, config: DevotionConfig) -> MeaningSignal | None:
    """Shown: each settled, successful showing of the item (as the statement item, or in
    the statement outfit) in the last ``shown_window_weeks`` game weeks earns one point per
    ``shown_engagements_per_point`` engagements, at most ``shown_max_points`` in all.
    Earned in a scene, so it has no carry gate."""
    from world.items.models import FashionShowing  # noqa: PLC0415

    showings = FashionShowing.objects.filter(settled=True, roll_success=True).filter(
        Q(statement_item=item) | Q(statement_outfit__slots__item_instance=item)
    )
    cutoff = _shown_cutoff(config.shown_window_weeks)
    if cutoff is not None:
        showings = showings.filter(created_at__gte=cutoff)
    per_point = max(config.shown_engagements_per_point, 1)
    rows = list(showings.distinct().values_list("pk", "engagement_count"))
    points = min(sum(count // per_point for _pk, count in rows), config.shown_max_points)
    if points <= 0:
        return None
    engagements = sum(count for _pk, count in rows)
    return MeaningSignal(
        MeaningSignalKind.SHOWN,
        points,
        f"{len(rows)} showing{'s' if len(rows) != 1 else ''}, {engagements} engaged",
    )


def _resonance_fed(
    item: ItemInstance, holder: CharacterSheet, being: WorshippedBeing, config: DevotionConfig
) -> MeaningSignal | None:
    """Resonance fed: what the item's attached facets have fed ``holder`` since they took
    it up, in resonances ``being`` lists. One point per ``resonance_fed_per_point`` fed in
    each resonance, doubled where the being favors it, up to ``resonance_fed_max_points``.

    Only grants to this holder's sheet on or after ``held_since`` count (a previous
    holder's stay on the item and score nothing), and only through facets still on the
    item: a removed facet (``removed_at``) is history, not meaning (#4461).
    """
    from django.db.models import Sum  # noqa: PLC0415

    from world.magic.constants import GainSource  # noqa: PLC0415
    from world.magic.models import ResonanceGrant  # noqa: PLC0415
    from world.worship.constants import BeingResonanceTier  # noqa: PLC0415

    tiers = dict(being.resonances.values_list("resonance_id", "tier"))
    if not tiers:
        return None
    fed = (
        ResonanceGrant.objects.filter(
            source=GainSource.OUTFIT_TRICKLE,
            character_sheet=holder,
            resonance_id__in=tiers,
            outfit_item_facet__item_instance=item,
            outfit_item_facet__removed_at__isnull=True,
            granted_at__gte=item.held_since,
        )
        .values("resonance_id", "resonance__name")
        .annotate(total=Sum("amount"))
    )
    per_point = max(config.resonance_fed_per_point, 1)
    points = 0
    parts: list[str] = []
    for row in fed:
        favored = tiers[row["resonance_id"]] == BeingResonanceTier.FAVORED
        earned = (row["total"] // per_point) * (2 if favored else 1)
        if earned > 0:
            points += earned
            parts.append(f"{row['total']} {row['resonance__name']}{', favored' if favored else ''}")
    points = min(points, config.resonance_fed_max_points)
    if points <= 0:
        return None
    return MeaningSignal(MeaningSignalKind.RESONANCE_FED, points, "fed " + "; ".join(parts))


def _trophy(
    item: ItemInstance, holder: CharacterSheet, config: DevotionConfig
) -> tuple[MeaningSignal | None, set[int]]:
    """Trophy: 1 plus the deed's legend over ``trophy_legend_per_point``, up to
    ``trophy_max_points``. The deed must be an active one credited to one of the holder's
    personas, so a trophy of someone else's deed (a piece passed on) scores nothing for the
    new holder. Earned by risk, so no carry gate. Also returns the deeds that counted."""
    deeds = list(item.legend_deeds.filter(is_active=True, persona__character_sheet=holder))
    if not deeds:
        return None, set()
    best = max(deeds, key=lambda deed: deed.get_total_value())
    per_point = max(config.trophy_legend_per_point, 1)
    points = min(1 + best.get_total_value() // per_point, config.trophy_max_points)
    if points <= 0:
        return None, set()
    return (
        MeaningSignal(MeaningSignalKind.TROPHY, points, f"won on {best.title}"),
        {deed.pk for deed in deeds},
    )


def _subject_points(
    keepsake: Keepsake, holder: CharacterSheet, config: DevotionConfig, trophy_deed_ids: set[int]
) -> int:
    """The points a keepsake's subject is worth: a tie's claimed tier, a deed's legend, or a
    flat point. 0 when the subject no longer belongs to the holder. The words are never
    read. A keepsake of a deed the item is also a trophy of adds a flat 1 on top of the
    trophy (the trophy already scored the deed)."""
    kind = keepsake.subject_kind
    cap = config.keepsake_max_points
    if kind == KeepsakeSubject.TIE:
        side = keepsake.subject_relationship
        if side is None or side.source_id != holder.pk:
            return 0
        return min(KEEPSAKE_BASE_POINTS + side.tier, cap)
    if kind == KeepsakeSubject.DEED:
        deed = keepsake.subject_deed
        if deed is None or not deed.is_active or deed.persona.character_sheet_id != holder.pk:
            return 0
        if deed.pk in trophy_deed_ids:
            return KEEPSAKE_BASE_POINTS
        scale = deed.get_total_value() // max(config.keepsake_deed_legend_per_point, 1)
        return min(KEEPSAKE_BASE_POINTS + scale, cap)
    return min(KEEPSAKE_BASE_POINTS, cap)


def _match_points(
    item: ItemInstance,
    keepsake: Keepsake,
    holder: CharacterSheet,
    being: WorshippedBeing | None,
) -> tuple[int, str]:
    """The keepsake match bonus and what matched: +``KEEPSAKE_BEING_MATCH_POINTS`` when the
    subject is the being the reading is for, or the tie's claimed tier when the subject is
    the tie with the item's giver or maker. (0, "") for neither."""
    if keepsake.subject_kind == KeepsakeSubject.BEING:
        if being is not None and keepsake.subject_being_id == being.pk:
            return KEEPSAKE_BEING_MATCH_POINTS, f"stands for {being.name}"
        return 0, ""
    if keepsake.subject_kind != KeepsakeSubject.TIE:
        return 0, ""
    side = keepsake.subject_relationship
    if side is None or side.target_id is None or side.tier <= 0:
        return 0, ""
    event = item.holding_event
    giver_pk = (
        event.from_character_sheet_id
        if event is not None and event.event_type == OwnershipEventType.GIVEN
        else None
    )
    maker_pks = {maker.pk for maker in _makers(item, holder)}
    if side.target_id == giver_pk:
        return side.tier, "the tie with the giver"
    if side.target_id in maker_pks:
        return side.tier, "the tie with the maker"
    return 0, ""


def keepsake_signals(  # noqa: PLR0913 - the reading context is keyword-only and distinct
    item: ItemInstance,
    holder: CharacterSheet,
    config: DevotionConfig,
    *,
    being: WorshippedBeing | None = None,
    trophy_deed_ids: set[int] | None = None,
    ignore_wait: bool = False,
) -> list[MeaningSignal]:
    """The keepsake and keepsake-match signals of ``item`` for ``holder`` (#4530).

    A keepsake counts once ``keepsake_wait_days`` have passed since it was declared, and
    only for the character who declared it. It scores its **subject** (see
    ``_subject_points``), never the words the player wrote. The detail names the subject.
    ``ignore_wait`` reads what it will be worth once the wait has passed (the admin's rail).
    """
    keepsake = item.keepsakes.filter(character_sheet=holder).first()
    if keepsake is None:
        return []
    if not ignore_wait and (timezone.now() - keepsake.created_at).days < config.keepsake_wait_days:
        return []
    points = _subject_points(keepsake, holder, config, trophy_deed_ids or set())
    if points <= 0:
        return []
    signals = [
        MeaningSignal(MeaningSignalKind.KEEPSAKE, points, f"stands for {keepsake.subject_name}")
    ]
    match, why = _match_points(item, keepsake, holder, being)
    if match > 0:
        signals.append(MeaningSignal(MeaningSignalKind.KEEPSAKE_MATCH, match, why))
    return signals


def item_meaning(
    item: ItemInstance,
    holder: CharacterSheet,
    *,
    config: DevotionConfig,
    being: WorshippedBeing | None = None,
) -> ItemMeaning:
    """The signals that make ``item`` matter to ``holder``, and so its meaning points.

    Pure of side effects. An item with no signal has no meaning, however it was paid for.
    ``config`` is the devotion config (the numbers are staff-tuned there); it is passed in
    so the items app does not import worship. ``being`` is the being the reading is for:
    the resonance fed signal reads the resonances that being lists, so without one it is
    left out. It counts only alongside another signal besides carried, and after the carry
    gate, so a bought piece worn for months still reads 0.
    """
    days = _carried_days(item)
    signals: list[MeaningSignal] = []
    if days >= config.sacrifice_min_carried_days:
        tie_counted_for: set[int] = set()
        made_signal, maker_pk = _made_by_tie(item, holder, config)
        if made_signal is not None and maker_pk is not None:
            signals.append(made_signal)
            tie_counted_for.add(maker_pk)
        personal = (
            _gift(item, holder, tie_counted_for),
            _made_for(item, holder, tie_counted_for, config),
            _heirloom(item),
            _designed(item, holder),
            _made_from(item, holder, config),
        )
        signals.extend(signal for signal in personal if signal is not None)
        if item.crafter_character_sheet_id == holder.pk:
            signals.append(MeaningSignal(MeaningSignalKind.OWN_WORK, 1, "made by the holder"))
    shown = _shown(item, config)
    if shown is not None:
        signals.append(shown)
    trophy, trophy_deed_ids = _trophy(item, holder, config)
    if trophy is not None:
        signals.append(trophy)
    signals.extend(
        keepsake_signals(item, holder, config, being=being, trophy_deed_ids=trophy_deed_ids)
    )
    if signals and being is not None and days >= config.sacrifice_min_carried_days:
        fed = _resonance_fed(item, holder, being, config)
        if fed is not None:
            signals.append(fed)
    if not signals:
        return ItemMeaning()
    carried = _carried(days, config)
    if carried is not None:
        signals.insert(0, carried)
    return ItemMeaning(tuple(signals))
