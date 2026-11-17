"""Fuzz: the Primum power curve and its split hold their contracts (#5125).

``points_to_power`` and ``apportion_power`` are pure, so they are fed arbitrary curves, points
and lines with no database. The properties are what casting relies on: more points never give
less power, power never passes the cap, a negative total is the mirror of a positive one, and a
split always adds up to the power it divides.
"""

from __future__ import annotations

import unittest

from hypothesis import given, strategies as st

from world.magic.constants import PrimumLineKind
from world.magic.services.primum import apportion_power, points_to_power
from world.magic.types.primum import SourcePoints


@st.composite
def curves(draw) -> list[tuple[int, int]]:
    """A curve with rising points and non-decreasing power, possibly empty."""
    xs = sorted(draw(st.sets(st.integers(1, 200), max_size=8)))
    ys = sorted(draw(st.lists(st.integers(0, 60), min_size=len(xs), max_size=len(xs))))
    return list(zip(xs, ys, strict=True))


points = st.integers(-1000, 1000)
caps = st.integers(0, 40)


class PointsToPowerHoldsItsContract(unittest.TestCase):
    @given(curves(), points, points, caps)
    def test_monotone_capped_and_odd(self, curve, a, b, cap) -> None:
        low, high = sorted((a, b))
        self.assertLessEqual(
            points_to_power(low, curve, cap=cap), points_to_power(high, curve, cap=cap)
        )
        for x in (a, b):
            result = points_to_power(x, curve, cap=cap)
            self.assertLessEqual(abs(result), cap)
            self.assertEqual(points_to_power(-x, curve, cap=cap), -result)


class ApportionPowerHoldsItsContract(unittest.TestCase):
    @given(st.lists(points, max_size=8), st.integers(-60, 60))
    def test_split_adds_up(self, line_points, total) -> None:
        lines = [
            SourcePoints(kind=PrimumLineKind.PLACE, label=str(i), points=p, substance_id=i)
            for i, p in enumerate(line_points)
        ]
        shares = apportion_power(lines, total)
        self.assertEqual(len(shares), len(lines))
        if any(line_points):
            self.assertEqual(sum(shares), total)
        else:
            self.assertEqual(shares, [0] * len(lines))
