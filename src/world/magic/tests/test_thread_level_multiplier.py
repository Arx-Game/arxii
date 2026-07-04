"""Tests for the consolidated, smoothed thread-level multiplier (#1718)."""

from decimal import Decimal

from django.test import TestCase

from world.magic.services.threads import thread_level_multiplier


class ThreadLevelMultiplierTests(TestCase):
    def test_level_one_is_the_old_floor(self):
        self.assertEqual(thread_level_multiplier(1), Decimal(1))

    def test_levels_one_through_nine_now_differ(self):
        values = [thread_level_multiplier(level) for level in range(1, 10)]
        self.assertEqual(len(set(values)), len(values), "levels 1-9 must all differ")
        self.assertEqual(values, sorted(values), "multiplier must be non-decreasing")

    def test_level_ten_matches_todays_anchor(self):
        # max(1, 10 // 10) == 1 today; the smoothed curve must still land on 1
        # exactly at the level-10 anchor (no regression above the low end).
        self.assertEqual(thread_level_multiplier(10), Decimal(1))

    def test_level_twenty_matches_todays_behavior_unchanged(self):
        # max(1, 20 // 10) == 2 today; level >= 10 must be byte-identical.
        self.assertEqual(thread_level_multiplier(20), Decimal(2))

    def test_level_zero_floors_at_one(self):
        self.assertEqual(thread_level_multiplier(0), Decimal(1))
