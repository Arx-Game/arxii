"""The stronger mark on a cast's resonance options holds its contract (#5231).

``stronger_marks`` is pure, so it is fed arbitrary strengths and a default entry with no
database. The journeys reach one shape (a kindled option above an unkindled default); this
covers the rest: a tie for the highest, a default that is itself the strongest, and a default
placed anywhere in the list, as a worn alternate self's resonance is.
"""

from __future__ import annotations

import unittest

from hypothesis import HealthCheck, given, settings, strategies as st

from world.magic.services.cast_resonance_options import stronger_marks

strength_lists = st.lists(st.integers(0, 40), min_size=1, max_size=8)


class StrongerMarksHoldTheirContract(unittest.TestCase):
    # Derandomized and deadline-free like the fuzz layer's ci profile; the test runner's
    # tracing makes generation slow enough to trip the too_slow health check.
    @settings(
        max_examples=100,
        deadline=None,
        derandomize=True,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(strength_lists, st.integers(0, 7))
    def test_one_entry_at_most_strictly_the_highest_and_above_the_default(
        self, strengths: list[int], default_pick: int
    ) -> None:
        default_index = default_pick % len(strengths)
        marks = stronger_marks(strengths, default_index)

        self.assertEqual(len(marks), len(strengths))
        self.assertLessEqual(sum(marks), 1)
        top = max(strengths)
        unique_top = strengths.count(top) == 1
        for index, marked in enumerate(marks):
            if marked:
                self.assertEqual(strengths[index], top)
                self.assertTrue(unique_top)
                self.assertGreater(strengths[index], strengths[default_index])
        # A tie for the highest, or a default that is itself the strongest, leaves nothing
        # marked (a mark needs a unique top above the default); nothing that qualifies is
        # left unmarked.
        if unique_top and top > strengths[default_index]:
            self.assertEqual(sum(marks), 1)
