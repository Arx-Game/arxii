"""
TDD tests for WeeklySocialEngagement pending ledger (Task 11 / B2)
and weekly grant service (Task 13 / B4).

Tests are written BEFORE the implementation — they should FAIL first.
"""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from evennia.accounts.models import AccountDB

from world.progression.factories import WeeklySocialEngagementFactory
from world.progression.models import KudosPointsData, KudosSourceCategory, WeeklySocialEngagement
from world.progression.services.engagement import accrue


class WeeklySocialEngagementFactoryTest(TestCase):
    """The factory must build cleanly — distinct_initiators is a derived property."""

    def test_factory_builds_with_derived_distinct_initiators(self) -> None:
        ledger = WeeklySocialEngagementFactory()
        # distinct_initiators is a read-only @property derived from child rows.
        self.assertEqual(ledger.distinct_initiators, 0)
        self.assertEqual(ledger.pending_points, Decimal(0))
        self.assertFalse(ledger.granted)


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


class WeeklyGrantKudosTest(TestCase):
    """Task 13 (B4): grant_social_engagement_kudos() — engagement-gated weekly grant.

    Tests written BEFORE implementation (TDD RED phase).
    """

    def setUp(self):
        WeeklySocialEngagement.flush_instance_cache()
        KudosPointsData.flush_instance_cache()
        KudosSourceCategory.flush_instance_cache()

        self.account = AccountDB.objects.create(
            username="grantee",
            email="grantee@example.com",
        )
        self.initiator_a = AccountDB.objects.create(
            username="grant_init_a",
            email="grant_init_a@example.com",
        )
        self.initiator_b = AccountDB.objects.create(
            username="grant_init_b",
            email="grant_init_b@example.com",
        )
        # KudosSourceCategory "social_engagement" must exist for award_kudos. It is
        # seeded by migration 0003 on the PG parity tier but absent on the SQLite fast
        # tier (which builds the schema from models, skipping data migrations), so
        # get_or_create works on both tiers.
        self.source_cat, _ = KudosSourceCategory.objects.get_or_create(
            name="social_engagement",
            defaults={
                "display_name": "Social Engagement",
                "description": "Weekly good-sport credit conversion.",
                "default_amount": 1,
                "is_active": True,
            },
        )

    def _make_qualifying_ledger(self, events: int = 4):
        """Create a ledger with *events* good-sport acceptances (curve attempts)."""
        for i in range(events):
            initiator = self.initiator_a if i % 2 == 0 else self.initiator_b
            accrue(self.account, initiator, Decimal("1.00"))
        return WeeklySocialEngagement.objects.get(account=self.account)

    def test_first_point_is_guaranteed(self):
        """Even if every roll fails, one good-sport act banks the guaranteed first point."""
        from world.progression.services import engagement as engagement_mod
        from world.progression.services.engagement import grant_social_engagement_kudos

        self._make_qualifying_ledger(events=3)

        # random.random()*100 == 99 fails the 80/60/… rolls but not the guaranteed 100% first.
        with patch.object(engagement_mod.random, "random", return_value=0.99):
            count = grant_social_engagement_kudos()

        self.assertEqual(count, 1)
        points_data = KudosPointsData.objects.get(account=self.account)
        self.assertEqual(points_data.total_earned, 1)

    def test_curve_caps_at_weekly_max(self):
        """With every roll succeeding, points bank up to the weekly cap and stop."""
        from world.progression.services import engagement as engagement_mod
        from world.progression.services.engagement import (
            GOOD_SPORT_WEEKLY_CAP,
            grant_social_engagement_kudos,
        )

        self._make_qualifying_ledger(events=50)

        with patch.object(engagement_mod.random, "random", return_value=0.0):
            grant_social_engagement_kudos()

        points_data = KudosPointsData.objects.get(account=self.account)
        self.assertEqual(points_data.total_earned, GOOD_SPORT_WEEKLY_CAP)

    def test_failed_roll_does_not_lower_chance(self):
        """A failed roll keeps points_locked unchanged, so the next roll's chance is the same."""
        from world.progression.services import engagement as engagement_mod
        from world.progression.services.engagement import grant_social_engagement_kudos

        self._make_qualifying_ledger(events=2)

        # First attempt guaranteed (+1, points_locked→1, chance 80). Second at 0.79*100=79 < 80.
        with patch.object(engagement_mod.random, "random", return_value=0.79):
            grant_social_engagement_kudos()

        points_data = KudosPointsData.objects.get(account=self.account)
        self.assertEqual(points_data.total_earned, 2)

    def test_zero_events_gets_no_grant(self):
        """A ledger with no good-sport acceptances is skipped and not marked granted."""
        from world.progression.services.engagement import grant_social_engagement_kudos

        ledger = WeeklySocialEngagementFactory(account=self.account)
        ledger.engagement_events = 0
        ledger.save(update_fields=["engagement_events"])

        count = grant_social_engagement_kudos()

        self.assertEqual(count, 0)
        ledger.refresh_from_db()
        self.assertFalse(ledger.granted)
        self.assertFalse(KudosPointsData.objects.filter(account=self.account).exists())

    def test_already_granted_ledger_skipped(self):
        """A ledger already marked granted=True is not re-granted."""
        from world.progression.services.engagement import grant_social_engagement_kudos

        ledger = self._make_qualifying_ledger(events=4)
        ledger.granted = True
        ledger.save(update_fields=["granted"])

        count = grant_social_engagement_kudos()

        self.assertEqual(count, 0)

    def test_weekly_rollover_task_fires_grant(self):
        """weekly_rollover_task() grants eligible ledgers when called."""
        from world.game_clock.tasks import weekly_rollover_task

        ledger = self._make_qualifying_ledger(events=6)
        self.assertFalse(ledger.granted)

        weekly_rollover_task()

        WeeklySocialEngagement.flush_instance_cache()
        ledger.refresh_from_db()
        self.assertTrue(ledger.granted)
        # The guaranteed first point means at least 1 kudos was earned.
        points_data = KudosPointsData.objects.get(account=self.account)
        self.assertGreaterEqual(points_data.total_earned, 1)
