"""Tests for reduce_pending_alteration_tier service (Scope 6 §5.7, §9.1)."""

from __future__ import annotations

from django.test import TestCase

from world.magic.constants import PendingAlterationStatus
from world.magic.factories import PendingAlterationFactory
from world.magic.models import MagicalAlterationEvent
from world.magic.services.alterations import reduce_pending_alteration_tier
from world.magic.types import AlterationResolutionError


class ReducePendingAlterationTierTests(TestCase):
    """Unit tests for reduce_pending_alteration_tier."""

    def test_reduction_below_tier_updates_field(self) -> None:
        """Reducing tier 3 by 1 yields new_tier=2, status stays OPEN."""
        pending = PendingAlterationFactory(tier=3)

        result = reduce_pending_alteration_tier(pending, amount=1, reason="treatment")

        pending.refresh_from_db()
        self.assertEqual(result.previous_tier, 3)
        self.assertEqual(result.new_tier, 2)
        self.assertFalse(result.resolved)
        self.assertEqual(pending.tier, 2)
        self.assertEqual(pending.status, PendingAlterationStatus.OPEN)

    def test_reduction_to_zero_marks_resolved_with_null_resolved_alteration(self) -> None:
        """When tier reaches 0, status becomes RESOLVED and resolved_alteration stays None."""
        pending = PendingAlterationFactory(tier=1)

        result = reduce_pending_alteration_tier(pending, amount=1, reason="treatment")

        pending.refresh_from_db()
        self.assertTrue(result.resolved)
        self.assertEqual(pending.status, PendingAlterationStatus.RESOLVED)
        self.assertIsNone(pending.resolved_alteration)

    def test_reduction_to_zero_stamps_resolved_at(self) -> None:
        """When tier reaches 0, resolved_at is populated."""
        pending = PendingAlterationFactory(tier=1)

        reduce_pending_alteration_tier(pending, amount=1, reason="treatment")

        pending.refresh_from_db()
        self.assertIsNotNone(pending.resolved_at)

    def test_reduction_to_zero_does_not_create_alteration_event(self) -> None:
        """No MagicalAlterationEvent is created when treatment resolves tier to 0."""
        pending = PendingAlterationFactory(tier=1)
        before = MagicalAlterationEvent.objects.count()

        reduce_pending_alteration_tier(pending, amount=1, reason="treatment")

        after = MagicalAlterationEvent.objects.count()
        self.assertEqual(before, after)

    def test_reduction_below_zero_clamps(self) -> None:
        """Reduction exceeding current tier clamps to 0 (no negative tier)."""
        pending = PendingAlterationFactory(tier=1)

        result = reduce_pending_alteration_tier(pending, amount=5, reason="treatment")

        pending.refresh_from_db()
        self.assertEqual(result.new_tier, 0)
        self.assertTrue(result.resolved)
        self.assertEqual(pending.tier, 0)

    def test_already_resolved_pending_raises_error(self) -> None:
        """Calling on a RESOLVED pending raises AlterationResolutionError."""
        pending = PendingAlterationFactory(
            tier=1,
            status=PendingAlterationStatus.RESOLVED,
        )

        with self.assertRaises(AlterationResolutionError):
            reduce_pending_alteration_tier(pending, amount=1, reason="treatment")
