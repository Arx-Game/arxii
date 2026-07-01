"""
Service functions for the weekly social-engagement pending ledger.
"""

from __future__ import annotations

from decimal import Decimal
import logging
import random

from django.db import transaction
from evennia.accounts.models import AccountDB

from world.progression.models.engagement import (
    WeeklyEngagementInitiator,
    WeeklySocialEngagement,
)

logger = logging.getLogger("world.progression.engagement")

# Good-sport weekly grant curve (#1698). Being a good sport about antagonism earns kudos
# with deliberately ambiguous, diminishing odds so nobody can count exactly how close they
# are to the weekly cap. The FIRST point of the week is guaranteed (100%); each further
# point is rolled at a lower chance, indexed by how many are already locked in this week —
# a FAILED roll does NOT lower the chance (only a banked point does). One roll per
# good-sport acceptance (``engagement_events``); the whole thing is silent.
GOOD_SPORT_CHANCE_BY_POINTS_LOCKED: tuple[int, ...] = (100, 80, 60, 40, 20)
# Chance (percent) for every attempt once >= len(curve) points are already locked in.
GOOD_SPORT_FLOOR_CHANCE: int = 10
# Maximum good-sport points a single account can bank in one week (across ALL antagonists —
# the counter is not per initiator→defender pair).
GOOD_SPORT_WEEKLY_CAP: int = 10


def _good_sport_chance(points_locked: int) -> int:
    """Percent chance the NEXT good-sport point lands, given points already banked this week."""
    if points_locked < len(GOOD_SPORT_CHANCE_BY_POINTS_LOCKED):
        return GOOD_SPORT_CHANCE_BY_POINTS_LOCKED[points_locked]
    return GOOD_SPORT_FLOOR_CHANCE


def _roll_good_sport_points(engagement_events: int) -> int:
    """Roll the diminishing-chance curve once per good-sport act; return points earned.

    The first attempt is guaranteed (100%), so any good sport with at least one accepted
    act this week banks at least one point. Capped at ``GOOD_SPORT_WEEKLY_CAP``.
    """
    points = 0
    for _ in range(engagement_events):
        if points >= GOOD_SPORT_WEEKLY_CAP:
            break
        if random.random() * 100 < _good_sport_chance(points):  # noqa: S311
            points += 1
    return points


def grant_social_engagement_kudos() -> int:
    """Grant good-sport Kudos from the week's accrued social engagement (#1698).

    For each ungranted ``WeeklySocialEngagement`` ledger, roll the diminishing-chance
    curve once per ``engagement_events`` (:func:`_roll_good_sport_points`): the first point
    of the week is guaranteed, each further point is rolled at a lower, ambiguous chance,
    and the weekly total is capped at ``GOOD_SPORT_WEEKLY_CAP``. Ledgers are marked
    ``granted`` regardless of the rolled amount (the week is resolved either way); kudos are
    only awarded when the roll yields > 0. Silent — the player is never told the odds or the
    running total. Errors on one ledger are logged, not fatal to the batch.

    Returns:
        The count of ledgers that were successfully granted kudos (amount > 0).
    """
    from world.progression.models import KudosSourceCategory
    from world.progression.services.kudos import award_kudos

    try:
        social_category = KudosSourceCategory.objects.get(name="social_engagement")
    except KudosSourceCategory.DoesNotExist:
        # Expected pre-launch state (category is DB-seeded separately) — warn, don't
        # log a traceback as if it were an error.
        logger.warning(
            "grant_social_engagement_kudos: KudosSourceCategory 'social_engagement' not found; "
            "skipping weekly grant."
        )
        return 0

    ungranted = list(WeeklySocialEngagement.objects.filter(granted=False))
    granted_count = 0

    for ledger in ungranted:
        if ledger.engagement_events <= 0:
            continue

        amount = _roll_good_sport_points(ledger.engagement_events)
        try:
            with transaction.atomic():
                if amount > 0:
                    award_kudos(
                        ledger.account,
                        amount,
                        social_category,
                        "Weekly good-sport kudos",
                    )
                ledger.granted = True
                ledger.save(update_fields=["granted"])
            if amount > 0:
                granted_count += 1
        except Exception:
            logger.exception(
                "grant_social_engagement_kudos: failed to grant ledger pk=%d (account=%s)",
                ledger.pk,
                ledger.account_id,
            )

    logger.info("grant_social_engagement_kudos: granted %d ledgers", granted_count)
    return granted_count


def accrue(
    account: AccountDB,
    initiator_account: AccountDB,
    points: Decimal,
) -> WeeklySocialEngagement:
    """
    Accrue social-engagement credit for *account* from *initiator_account*.

    - Gets or creates the weekly ledger for *account*.
    - Resets it if the game week has changed (lazy reset on read, mirroring
      the ``_get_or_reset_weekly_tracker`` pattern in journals/services.py).
    - Adds *points* to ``pending_points``.
    - If this is the first accrual from *initiator_account* this week,
      creates a ``WeeklyEngagementInitiator`` row (``distinct_initiators``
      is derived from those rows).  A second accrual from the same initiator
      adds points but creates no duplicate row, so it does NOT double-count.

    Args:
        account: The account receiving the engagement credit.
        initiator_account: The account originating the credit.
        points: Positive decimal amount to add to the ledger.

    Returns:
        The updated ``WeeklySocialEngagement`` ledger instance.
    """
    from world.game_clock.week_services import get_current_game_week

    with transaction.atomic():
        current_week = get_current_game_week()
        ledger, created = WeeklySocialEngagement.objects.select_for_update().get_or_create(
            account=account,
            defaults={"game_week": current_week},
        )
        if not created and ledger.needs_reset(current_week):
            ledger.reset_week(current_week)

        ledger.pending_points += points
        # Each accrual is one good-sport act = one attempt in the weekly grant curve (#1698).
        ledger.engagement_events += 1

        # Record distinct initiator — get_or_create deduplicates; count derived from child rows.
        WeeklyEngagementInitiator.objects.get_or_create(
            ledger=ledger,
            initiator_account=initiator_account,
        )

        ledger.save(update_fields=["pending_points", "engagement_events"])

    return ledger
