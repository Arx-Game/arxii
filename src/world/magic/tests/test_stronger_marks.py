"""The stronger mark on a resonance option list holds its contract (#5231).

``stronger_marks`` is pure, so it is fed arbitrary strengths and baselines with no database. It
is the one rule behind both lists: a cast's resonance options (every entry's baseline is the
default entry's strength) and a pull's payer options (each entry's baseline is its own unboosted
read, and a payer with no perks does not compete). The journeys reach one shape of each; this
covers the rest: a tie for the highest, a baseline that is itself the strongest, a baseline
placed anywhere in the list, and an entry that does not compete.
"""

from __future__ import annotations

import unittest

from hypothesis import HealthCheck, given, settings, strategies as st

from world.magic.services.kindled_math import stronger_marks

# One entry: a strength (None = it does not compete) and the baseline it must beat.
entries = st.lists(
    st.tuples(st.one_of(st.none(), st.integers(0, 40)), st.integers(0, 40)),
    min_size=1,
    max_size=8,
)


class StrongerMarksHoldTheirContract(unittest.TestCase):
    # Derandomized and deadline-free like the fuzz layer's ci profile; the test runner's
    # tracing makes generation slow enough to trip the too_slow health check.
    @settings(
        max_examples=200,
        deadline=None,
        derandomize=True,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(entries)
    def test_one_entry_at_most_strictly_the_highest_and_above_its_own_baseline(
        self, pairs: list[tuple[int | None, int]]
    ) -> None:
        strengths = [strength for strength, _baseline in pairs]
        baselines = [baseline for _strength, baseline in pairs]
        marks = stronger_marks(strengths, baselines)

        competing = [strength for strength in strengths if strength is not None]
        top = max(competing, default=0)
        unique_top = competing.count(top) == 1
        self.assertEqual(len(marks), len(strengths))
        self.assertLessEqual(sum(marks), 1)
        for index, marked in enumerate(marks):
            if marked:
                self.assertIsNotNone(strengths[index])
                self.assertEqual(strengths[index], top)
                self.assertTrue(unique_top)
                self.assertGreater(strengths[index], baselines[index])
        # A tie for the highest, or a leader no stronger than its own baseline, leaves
        # nothing marked; nothing that qualifies is left unmarked.
        if competing and unique_top:
            leader = strengths.index(top)
            self.assertEqual(sum(marks), 1 if top > baselines[leader] else 0)
        else:
            self.assertEqual(sum(marks), 0)
