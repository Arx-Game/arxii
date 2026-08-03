"""Showcase + cachet + weekly settlement (#2907).

The modeling economy's spine: a persistent showcase toggle, cachet staked
automatically when a showcasing character makes an entrance, and a
weekly-cron settlement (NEVER immediate — the anti-farm keystone: the week is
evaluated, not the entrance; empty-room farming settles to break-even
forever). Apostate's ladder, verbatim: a good roll refunds the stake; real
player engagement pays +1; overwhelming engagement +1 more.

Prestige/legend discipline: settlement loads ACCLAIM (prestige-side, can
drop, compounding) onto statements — it never mints legend (legend is for
life-risking deeds only).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import F

from world.items.constants import (
    SETTLEMENT_ENGAGEMENT_BONUS,
    SETTLEMENT_MAX_PAYOUT_SCENE,
    SETTLEMENT_OVERWHELMING_THRESHOLD,
    SHOWCASE_STAKE_EVENT,
    SHOWCASE_STAKE_SCENE,
    VOGUE_PUSH_PER_PAYOUT,
    VOGUE_WEEKLY_DECAY,
    ShowcaseMode,
)
from world.items.models import (
    CachetWallet,
    FashionShowing,
    ShowcaseState,
    SilhouetteVogueMomentum,
    StyleVogueMomentum,
)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.scenes.models import Scene

logger = logging.getLogger(__name__)


def get_or_create_wallet(sheet: CharacterSheet) -> CachetWallet:
    """The sheet's cachet wallet (created at the starting balance)."""
    wallet, _ = CachetWallet.objects.get_or_create(character_sheet=sheet)
    return wallet


def record_showcase_showing(
    sheet: CharacterSheet,
    *,
    scene: Scene | None,
    roll_success: bool,
    at_event: bool = False,
) -> FashionShowing | None:
    """Stake cachet for an entrance made while showcasing, or None.

    Called from the entrance path AFTER the social check resolves. Never
    blocks or fails the entrance itself: no active showcase, or an
    unaffordable stake, simply records nothing. The stake deducts
    immediately; every payout waits for the weekly settlement.
    """
    state = ShowcaseState.objects.filter(character_sheet=sheet, is_active=True).first()
    if state is None:
        return None
    stake = SHOWCASE_STAKE_EVENT if at_event else SHOWCASE_STAKE_SCENE
    wallet = get_or_create_wallet(sheet)
    if wallet.balance < stake:
        return None

    statement_item = state.item if state.mode == ShowcaseMode.PIECE else None
    statement_outfit = state.outfit if state.mode == ShowcaseMode.ENSEMBLE else None
    # The statement's vocabulary: a PIECE pushes its style AND silhouette; an
    # ENSEMBLE pushes the outfit's style (v1: the first styled piece's style —
    # outfit-level style aggregation is a flagged open item).
    statement_style = None
    statement_silhouette = None
    if statement_item is not None:
        statement_silhouette = statement_item.effective_silhouette
        first_style = statement_item.item_styles.select_related("style").first()
        statement_style = first_style.style if first_style else None
    elif statement_outfit is not None:
        for slot in statement_outfit.slots.select_related("item_instance").all():
            first_style = slot.item_instance.item_styles.select_related("style").first()
            if first_style is not None:
                statement_style = first_style.style
                break

    with transaction.atomic():
        wallet.balance = F("balance") - stake
        wallet.save(update_fields=["balance"])
        wallet.refresh_from_db(fields=["balance"])
        return FashionShowing.objects.create(
            character_sheet=sheet,
            scene=scene,
            mode=state.mode,
            statement_item=statement_item,
            statement_outfit=statement_outfit,
            statement_style=statement_style,
            statement_silhouette=statement_silhouette,
            stake=stake,
            roll_success=roll_success,
        )


def record_showing_engagement(showing: FashionShowing) -> None:
    """Bump peer engagement on an unsettled showing (endorsements etc.)."""
    if showing.settled:
        return
    FashionShowing.objects.filter(pk=showing.pk).update(engagement_count=F("engagement_count") + 1)


def _settle_one(showing: FashionShowing) -> int:
    """Apply the payout ladder to one showing; returns the payout."""
    payout = 0
    if showing.roll_success:
        payout += showing.stake  # the refund leg — break-even for a good roll
    if showing.engagement_count > 0:
        payout += SETTLEMENT_ENGAGEMENT_BONUS
    if showing.engagement_count >= SETTLEMENT_OVERWHELMING_THRESHOLD:
        payout += SETTLEMENT_ENGAGEMENT_BONUS
    # Cap relative to the stake so event-tier stakes keep their scale: the
    # scene cap is 3 (stake 1 + 2 engagement legs).
    payout = min(payout, showing.stake + SETTLEMENT_MAX_PAYOUT_SCENE - 1)

    showing.payout = payout
    showing.settled = True
    showing.save(update_fields=["payout", "settled"])

    if payout > 0:
        wallet = get_or_create_wallet(showing.character_sheet)
        wallet.balance = F("balance") + payout
        wallet.save(update_fields=["balance"])
        wallet.refresh_from_db(fields=["balance"])

    # Acclaim (prestige-side, never legend) + vogue push scale with the
    # engagement legs only — a lonely good roll refunds but moves nothing.
    engaged_payout = max(0, payout - (showing.stake if showing.roll_success else 0))
    if engaged_payout > 0:
        if showing.statement_item is not None:
            type(showing.statement_item).objects.filter(pk=showing.statement_item.pk).update(
                acclaim=F("acclaim") + engaged_payout
            )
        if showing.statement_outfit is not None:
            type(showing.statement_outfit).objects.filter(pk=showing.statement_outfit.pk).update(
                acclaim=F("acclaim") + engaged_payout
            )
        push = engaged_payout * VOGUE_PUSH_PER_PAYOUT
        if showing.statement_silhouette is not None:
            row, _ = SilhouetteVogueMomentum.objects.get_or_create(
                silhouette=showing.statement_silhouette
            )
            SilhouetteVogueMomentum.objects.filter(pk=row.pk).update(points=F("points") + push)
        if showing.statement_style is not None:
            row, _ = StyleVogueMomentum.objects.get_or_create(style=showing.statement_style)
            StyleVogueMomentum.objects.filter(pk=row.pk).update(points=F("points") + push)
    return payout


def settle_fashion_showings() -> int:
    """Weekly settlement processor: settle every unsettled showing, decay vogue.

    Registered in ``weekly_rollover_task``. Returns the number settled.
    """
    # Decay FIRST (seasonal-slow; guess flagged on #2907): last week's heat
    # fades, THEN this week's showings land — same-run decay must never wipe
    # freshly-settled momentum.
    for row in SilhouetteVogueMomentum.objects.filter(points__gt=0):
        row.points = int(row.points * VOGUE_WEEKLY_DECAY)
        row.save(update_fields=["points"])
    for row in StyleVogueMomentum.objects.filter(points__gt=0):
        row.points = int(row.points * VOGUE_WEEKLY_DECAY)
        row.save(update_fields=["points"])

    settled = 0
    for showing in FashionShowing.objects.filter(settled=False).select_related(
        "character_sheet", "statement_item", "statement_outfit"
    ):
        _settle_one(showing)
        settled += 1

    if settled:
        logger.info("Fashion settlement: %d showings settled.", settled)
    return settled
