"""Tests for Resonance Pivot Spec A Phase 3 lookup tables.

Covers ThreadPullCost, ThreadXPLockedLevel, ThreadPullEffect,
ImbuingProseTemplate, and Ritual / RitualComponentRequirement.
"""

from django.db.utils import IntegrityError
from django.test import TestCase

from world.magic.factories import ThreadPullCostFactory
from world.magic.models import ThreadPullCost


class ThreadPullCostModelTests(TestCase):
    def test_three_launch_tiers_exist_after_factory_setup(self):
        tier1 = ThreadPullCostFactory(tier=1, resonance_cost=1, anima_per_thread=1, label="soft")
        tier2 = ThreadPullCostFactory(tier=2, resonance_cost=3, anima_per_thread=2, label="hard")
        tier3 = ThreadPullCostFactory(tier=3, resonance_cost=6, anima_per_thread=3, label="max")
        self.assertEqual(ThreadPullCost.objects.count(), 3)
        self.assertEqual({c.tier for c in (tier1, tier2, tier3)}, {1, 2, 3})

    def test_tier_is_unique(self):
        ThreadPullCostFactory(tier=1)
        with self.assertRaises(IntegrityError):
            # Force a new insert (django_get_or_create would normally just fetch).
            ThreadPullCost.objects.create(tier=1, resonance_cost=2, anima_per_thread=2, label="dup")
