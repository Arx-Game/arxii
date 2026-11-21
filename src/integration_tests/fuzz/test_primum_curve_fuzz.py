"""Fuzz: the Primum power curve and its split hold their contracts (#5125).

``points_to_power`` and ``apportion_power`` are pure, so they are fed arbitrary curves, points
and lines with no database. The properties are what casting relies on: more points never give
less power, power never passes the cap, a negative total is the mirror of a positive one, and a
split always adds up to the power it divides. Three more rules come straight from the
docstrings: the curve passes through every one of its own rows, between two rows it is the
straight line (starting from the point 0, 0), and the split is the textbook largest-remainder
split, worked here in exact fractions, for the helping lines and the opposing lines together.
"""

from __future__ import annotations

from fractions import Fraction
from itertools import pairwise
from math import floor
import unittest

from hypothesis import example, given, strategies as st

from world.magic.constants import PrimumLineKind
from world.magic.services.primum import apportion_power, points_to_power, total_points
from world.magic.types.primum import SourcePoints


@st.composite
def curves(draw) -> list[tuple[int, int]]:
    """A curve with rising points and non-decreasing power, possibly empty."""
    xs = sorted(draw(st.sets(st.one_of(st.integers(1, 6), st.integers(1, 200)), max_size=8)))
    ys = sorted(draw(st.lists(st.integers(0, 60), min_size=len(xs), max_size=len(xs))))
    return list(zip(xs, ys, strict=True))


points = st.integers(-1000, 1000)
caps = st.integers(0, 40)


@st.composite
def curve_with_totals(draw) -> tuple[list[tuple[int, int]], int, int]:
    """A curve and two totals. Each total is drawn wide, inside the curve's own range, or tiny."""
    curve = draw(curves())
    reach = curve[-1][0] if curve else 0
    total = st.one_of(points, st.integers(-reach, reach), st.integers(-3, 3))
    return curve, draw(total), draw(total)


def _exact_power(magnitude: int, curve: list[tuple[int, int]]) -> Fraction:
    """The straight line from (0, 0) through the rows, at a magnitude inside the curve."""
    for (x0, y0), (x1, y1) in pairwise([(0, 0), *curve]):
        if x0 <= magnitude <= x1:
            return y0 + Fraction((magnitude - x0) * (y1 - y0), x1 - x0)
    msg = "the magnitude is past the last row"
    raise AssertionError(msg)


def _by_largest_remainder(weights: list[int], amount: int) -> list[int]:
    """The textbook split that ``_largest_remainder`` names, worked in exact fractions.

    The docstring of ``_largest_remainder`` says: "Split ``amount`` over ``weights`` by the
    largest remainder, earlier entries first on a tie." Each entry's exact quota is rounded
    down, then what is left over is handed out one each to the largest fractional parts, the
    earlier entry first on a tie.
    """
    weight_sum = sum(weights)
    if weight_sum == 0:
        return [0] * len(weights)
    quotas = [Fraction(amount * weight, weight_sum) for weight in weights]
    shares = [floor(quota) for quota in quotas]
    by_fraction = sorted(range(len(weights)), key=lambda i: (shares[i] - quotas[i], i))
    for i in by_fraction[: amount - sum(shares)]:
        shares[i] += 1
    return shares


class PointsToPowerHoldsItsContract(unittest.TestCase):
    @given(curve_with_totals(), caps)
    def test_monotone_capped_and_odd(self, curve_and_totals, cap) -> None:
        curve, a, b = curve_and_totals
        low, high = sorted((a, b))
        self.assertLessEqual(
            points_to_power(low, curve, cap=cap), points_to_power(high, curve, cap=cap)
        )
        for x in (a, b):
            result = points_to_power(x, curve, cap=cap)
            self.assertLessEqual(abs(result), cap)
            self.assertEqual(points_to_power(-x, curve, cap=cap), -result)

    @given(curves(), caps)
    def test_curve_passes_through_its_rows(self, curve, cap) -> None:
        """Reaching a row of the curve gives that row's power, or the cap when that is lower.

        The docstring of ``points_to_power`` calls the curve "a list of ``(points_reached,
        power)``" and says it is "Linear between the rows". Both together say that reaching a
        row gives that row's power. It also says "The result never passes ``cap`` either way",
        so a row whose power is over the cap reads as the cap.
        """
        for reached, power in curve:
            self.assertEqual(points_to_power(reached, curve, cap=cap), min(power, cap))

    @given(curve_with_totals(), caps)
    # These two cases check one point and minus one point, on a curve whose first row is at one.
    @example(([(1, 1)], 1, 1), 1)
    @example(([(1, 1)], -1, -1), 1)
    # This case sits half way up the first segment, so the exact power is one half and rounds down.
    @example(([(2, 1)], 1, 0), 1)
    def test_between_rows_it_is_the_straight_line(self, curve_and_totals, cap) -> None:
        """The docstring of ``points_to_power`` says the curve is as follows.

        "Linear between the rows, starting from (0, 0), flat after the last row. A negative
        total mirrors the positive one." It also says "No rows gives 0."
        """
        curve, total, _ = curve_and_totals
        result = points_to_power(total, curve, cap=cap)
        self.assertIs(type(result), int)
        self.assertGreaterEqual(result * total, 0)
        magnitude = abs(total)
        if not curve or magnitude == 0:
            self.assertEqual(result, 0)
            return
        if magnitude >= curve[-1][0]:
            self.assertEqual(abs(result), min(curve[-1][1], cap))
            return
        exact = _exact_power(magnitude, curve)
        # The ``points_to_power`` docstring says "A value between two rows is rounded down
        # before the sign is applied (#4248)."
        self.assertEqual(abs(result), min(floor(exact), cap))


class ApportionPowerHoldsItsContract(unittest.TestCase):
    @given(st.lists(points, max_size=8))
    def test_total_points_is_the_signed_sum(self, line_points) -> None:
        """``total_points`` gives "The signed points of every line added together."

        A helping line of 7 and an opposing line of -2 total 5, and with every line's points
        negated the total is the negation.
        """

        def lines_of(values: list[int]) -> list[SourcePoints]:
            return [
                SourcePoints(kind=PrimumLineKind.PLACE, label=str(i), points=p, substance_id=i)
                for i, p in enumerate(values)
            ]

        self.assertEqual(total_points(lines_of(line_points)), sum(line_points))
        self.assertEqual(total_points(lines_of([-p for p in line_points])), -sum(line_points))

    @given(
        st.lists(points, max_size=8),
        st.integers(0, 60),
        st.integers(0, 60),
    )
    def test_split_keeps_signs_and_adds_up(self, line_points, gained, lost) -> None:
        lines = [
            SourcePoints(kind=PrimumLineKind.PLACE, label=str(i), points=p, substance_id=i)
            for i, p in enumerate(line_points)
        ]
        # There is no positive power without a positive line, and no loss without a negative line.
        positive_power = gained if any(p > 0 for p in line_points) else 0
        negative_power = lost if any(p < 0 for p in line_points) else 0
        total = positive_power - negative_power
        shares = apportion_power(lines, total, positive_power=positive_power)
        self.assertEqual(len(shares), len(lines))
        self.assertEqual(sum(shares), total)
        for line, share in zip(lines, shares, strict=True):
            if line.points > 0:
                self.assertGreaterEqual(share, 0)
            elif line.points < 0:
                self.assertLessEqual(share, 0)
            else:
                self.assertEqual(share, 0)

    @given(
        st.one_of(
            st.lists(points, max_size=8),
            st.lists(st.integers(-4, 4), max_size=8),
            st.lists(st.integers(-1, 1), max_size=4),
        ),
        st.integers(0, 60),
        st.integers(0, 60),
    )
    # A single source worth one point, or minus one point, takes the whole amount.
    @example([1], 1, 0)
    @example([-1], 0, 1)
    def test_split_follows_its_docstring_exactly(self, line_points, gained, lost) -> None:
        lines = [
            SourcePoints(kind=PrimumLineKind.PLACE, label=str(i), points=p, substance_id=i)
            for i, p in enumerate(line_points)
        ]
        positive_power = gained if any(p > 0 for p in line_points) else 0
        negative_power = lost if any(p < 0 for p in line_points) else 0
        total = positive_power - negative_power
        # The split rule is quoted from ``apportion_power``: "Lines with positive points split it
        # by their points; lines with negative points split what they take away,
        # ``positive_power - total_power``, by their points, and each share is negated; a line
        # worth no points gets 0." The largest-remainder rule and its tie order are quoted from
        # ``_largest_remainder`` in ``_by_largest_remainder``. The amount to lose is never
        # negative here: there is no positive power without a positive line and no loss without
        # a negative line, so it is ``negative_power``, which is 0 or more.
        gains = _by_largest_remainder([max(0, p) for p in line_points], positive_power)
        losses = _by_largest_remainder([max(0, -p) for p in line_points], negative_power)
        expected = [gain - loss for gain, loss in zip(gains, losses, strict=True)]
        self.assertEqual(apportion_power(lines, total, positive_power=positive_power), expected)
