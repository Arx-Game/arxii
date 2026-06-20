"""
TDD tests for WeeklySocialEngagement pending ledger (Task 11 / B2).

Tests are written BEFORE the implementation — they should FAIL first.
"""

from decimal import Decimal

from django.test import TestCase
from evennia.accounts.models import AccountDB

from world.progression.models import WeeklySocialEngagement
from world.progression.services.engagement import accrue


class WeeklySocialEngagementAccrueTest(TestCase):
    """Test accrue() service and distinct-initiator de-duplication."""

    def setUp(self):
        # Use direct AccountDB.objects.create — same pattern as test_kudos.py.
        # Flush idmapper cache to prevent cross-test pollution.
        WeeklySocialEngagement.flush_instance_cache()

        self.account = AccountDB.objects.create(
            username="recipient",
            email="recipient@example.com",
        )
        self.initiator_a = AccountDB.objects.create(
            username="initiator_a",
            email="initiator_a@example.com",
        )
        self.initiator_b = AccountDB.objects.create(
            username="initiator_b",
            email="initiator_b@example.com",
        )

    def test_same_initiator_counted_once(self):
        """Two accruals from the same initiator yield distinct_initiators == 1."""
        accrue(self.account, self.initiator_a, Decimal("5.00"))
        ledger = accrue(self.account, self.initiator_a, Decimal("3.00"))

        ledger.refresh_from_db()
        self.assertEqual(ledger.distinct_initiators, 1)
        self.assertEqual(ledger.pending_points, Decimal("8.00"))

    def test_two_different_initiators_counted_separately(self):
        """Two accruals from different initiators yield distinct_initiators == 2."""
        accrue(self.account, self.initiator_a, Decimal("5.00"))
        ledger = accrue(self.account, self.initiator_b, Decimal("3.00"))

        ledger.refresh_from_db()
        self.assertEqual(ledger.distinct_initiators, 2)
        self.assertEqual(ledger.pending_points, Decimal("8.00"))

    def test_reset_week_clears_ledger(self):
        """reset_week() zeroes all counters and deletes child initiator rows."""
        from world.game_clock.week_services import advance_game_week

        # Accrue in the current week
        accrue(self.account, self.initiator_a, Decimal("10.00"))
        ledger = WeeklySocialEngagement.objects.get(account=self.account)
        self.assertEqual(ledger.distinct_initiators, 1)

        # Advance game week then reset
        new_week = advance_game_week()
        ledger.refresh_from_db()
        ledger.reset_week(new_week)

        ledger.refresh_from_db()
        self.assertEqual(ledger.pending_points, Decimal(0))
        self.assertEqual(ledger.distinct_initiators, 0)
        self.assertFalse(ledger.granted)
        # Child initiator rows must be cleared
        self.assertEqual(ledger.initiators.count(), 0)

    def test_new_week_via_accrue_resets_ledger(self):
        """After week advances, the next accrue() call resets the ledger automatically."""
        from world.game_clock.week_services import advance_game_week

        accrue(self.account, self.initiator_a, Decimal("7.00"))

        advance_game_week()

        ledger = accrue(self.account, self.initiator_b, Decimal("4.00"))
        ledger.refresh_from_db()

        # Old week's points gone; fresh accrual only
        self.assertEqual(ledger.pending_points, Decimal("4.00"))
        self.assertEqual(ledger.distinct_initiators, 1)

    def test_granted_defaults_false(self):
        """Freshly created ledger has granted=False."""
        ledger = accrue(self.account, self.initiator_a, Decimal("1.00"))
        self.assertFalse(ledger.granted)
