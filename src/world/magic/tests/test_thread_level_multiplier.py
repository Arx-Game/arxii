"""Tests for the consolidated, smoothed thread-level multiplier (#1718)."""

from decimal import Decimal

from django.test import TestCase

from world.magic.services.threads import thread_level_multiplier


class ThreadLevelMultiplierTests(TestCase):
    def test_level_one_ramps_below_old_floor(self):
        # The corrected linear ramp (0.1 at level 1 → 1.0 at level 10) scores
        # level 1 BELOW the old flat floor of 1, not at or above it. The
        # earlier (buggy) formula returned 1 here; that formula overshot the
        # level-10 anchor further up the curve (level 9 > level 10), a real
        # gameplay regression caught in review. This lower level-1 value is
        # the deliberate tradeoff that avoids that regression.
        self.assertEqual(thread_level_multiplier(1), Decimal("0.1"))

    def test_levels_one_through_nine_now_differ(self):
        values = [thread_level_multiplier(level) for level in range(1, 10)]
        self.assertEqual(len(set(values)), len(values), "levels 1-9 must all differ")
        self.assertEqual(values, sorted(values), "multiplier must be non-decreasing")

    def test_level_ten_matches_todays_anchor(self):
        # max(1, 10 // 10) == 1 today; the smoothed curve must still land on 1
        # exactly at the level-10 anchor (no regression above the low end).
        self.assertEqual(thread_level_multiplier(10), Decimal(1))

    def test_level_nine_does_not_exceed_level_ten(self):
        # The regression this fix closes: the earlier formula overshot the
        # level-10 anchor, so a thread advancing 9 -> 10 got a SMALLER
        # multiplier. Pin down both the strict ordering and the anchor value
        # so neither can silently regress again.
        self.assertLess(thread_level_multiplier(9), thread_level_multiplier(10))
        self.assertEqual(thread_level_multiplier(10), Decimal(1))

    def test_level_twenty_matches_todays_behavior_unchanged(self):
        # max(1, 20 // 10) == 2 today; level >= 10 must be byte-identical.
        self.assertEqual(thread_level_multiplier(20), Decimal(2))

    def test_level_zero_floors_at_one(self):
        self.assertEqual(thread_level_multiplier(0), Decimal(1))
