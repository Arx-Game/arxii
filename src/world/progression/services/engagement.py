"""
Service functions for the weekly social-engagement pending ledger.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from evennia.accounts.models import AccountDB

from world.progression.models.engagement import WeeklyEngagementInitiator, WeeklySocialEngagement


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
      creates a ``WeeklyEngagementInitiator`` row and increments
      ``distinct_initiators``.  A second accrual from the same initiator
      adds points but does NOT double-count.

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

        # Track distinct initiator — create row if new, skip if already seen.
        _, initiator_created = WeeklyEngagementInitiator.objects.get_or_create(
            ledger=ledger,
            initiator_account=initiator_account,
        )
        if initiator_created:
            ledger.distinct_initiators += 1

        ledger.save(update_fields=["pending_points", "distinct_initiators"])

    return ledger
