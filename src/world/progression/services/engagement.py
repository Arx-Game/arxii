"""
Service functions for the weekly social-engagement pending ledger.
"""

from __future__ import annotations

from decimal import Decimal
import logging

from django.db import transaction
from evennia.accounts.models import AccountDB

from world.progression.models.engagement import (
    WeeklyEngagementInitiator,
    WeeklySocialEngagement,
)

logger = logging.getLogger("world.progression.engagement")

# Tunable constants for the weekly good-sport kudos grant.
# MIN_ENGAGEMENT_BAR: minimum distinct initiators required to qualify.
# Filters single-yes token-farming (one account alone cannot self-grant).
MIN_ENGAGEMENT_BAR: int = 2

# WEEKLY_KUDOS_SCALE: multiplier applied to pending_points before rounding.
# Adjust to tune weekly kudos yield without touching the accrual weights.
WEEKLY_KUDOS_SCALE: Decimal = Decimal(1)


def grant_social_engagement_kudos() -> int:
    """Grant Kudos from accrued weekly social-engagement credit.

    For each ungranted ``WeeklySocialEngagement`` ledger:

    - Skips ledgers below ``MIN_ENGAGEMENT_BAR`` distinct initiators
      (prevents single-account token-farming).
    - Computes ``amount = int(round(pending_points * WEEKLY_KUDOS_SCALE))``.
    - If amount > 0: awards kudos and marks the ledger ``granted=True``.
    - If amount == 0 or below the bar: leaves ``granted=False`` (no grant).

    Errors on individual ledgers are caught and logged so one bad row
    does not abort the batch.

    Returns:
        The count of ledgers that were successfully granted.
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
        if ledger.distinct_initiators < MIN_ENGAGEMENT_BAR:
            continue

        amount = round(ledger.pending_points * WEEKLY_KUDOS_SCALE)
        if amount <= 0:
            continue

        try:
            with transaction.atomic():
                award_kudos(
                    ledger.account,
                    amount,
                    social_category,
                    "Weekly good-sport kudos",
                )
                ledger.granted = True
                ledger.save(update_fields=["granted"])
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

        # Record distinct initiator — get_or_create deduplicates; count derived from child rows.
        WeeklyEngagementInitiator.objects.get_or_create(
            ledger=ledger,
            initiator_account=initiator_account,
        )

        ledger.save(update_fields=["pending_points"])

    return ledger
