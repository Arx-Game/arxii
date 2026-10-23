"""Guard: the result-chart ladder must never invert again (#2707).

`rank_difference = roller_rank - target_rank`, so a POSITIVE difference means
the roller is stronger and must select an EASIER chart. This inverted silently
for the whole life of the project because nothing asserted direction.
"""

from django.test import TestCase

from world.checks.services import chart_has_success_outcomes
from world.seeds.checks import seed_check_resolution_tables
from world.traits.models import CheckOutcome, CheckRank, ResultChart, ResultChartOutcome


def _success_share(roller_points: int, target_difficulty: int) -> int:
    """Rolls (out of 100) that produce a success_level > 0 for this matchup."""
    roller_rank = CheckRank.get_rank_for_points(roller_points)
    target_rank = CheckRank.get_rank_for_points(target_difficulty)
    rank_difference = (roller_rank.rank if roller_rank else 0) - (
        target_rank.rank if target_rank else 0
    )
    chart = ResultChart.get_chart_for_difference(rank_difference)
    assert chart is not None
    rows = ResultChartOutcome.objects.filter(chart=chart).select_related("outcome")
    return sum(row.max_roll - row.min_roll + 1 for row in rows if row.outcome.success_level > 0)


class ChartDirectionTests(TestCase):
    """Being better at something must not make you fail more."""

    def setUp(self):
        seed_check_resolution_tables()
        ResultChart.clear_cache()

    def test_stronger_roller_gets_better_odds_than_weaker_roller(self):
        strong = _success_share(roller_points=60, target_difficulty=0)
        weak = _success_share(roller_points=0, target_difficulty=60)
        self.assertGreater(strong, weak)

    def test_success_odds_are_monotonic_in_roller_strength(self):
        """Holding difficulty fixed, more points must never mean fewer successes."""
        shares = [
            _success_share(roller_points=pts, target_difficulty=25)
            for pts in (0, 10, 25, 50, 80, 115, 155)
        ]
        self.assertEqual(shares, sorted(shares))

    def test_success_odds_are_monotonic_in_difficulty(self):
        """Holding the roller fixed, a harder target must never mean more successes."""
        shares = [
            _success_share(roller_points=50, target_difficulty=d)
            for d in (0, 10, 25, 50, 80, 115, 155)
        ]
        self.assertEqual(shares, sorted(shares, reverse=True))

    def test_deep_gap_degrades_effect_and_never_improves_on_a_wider_gap(self):
        """A wider gap never offers better odds; -5 chips away rather than whiffs (#2707, #4593).

        Chance of any non-failure outcome is flat at 55% from -5 to -2 (the repaired
        charts), while the Success share keeps shrinking with depth. What degrades with
        depth is what you accomplish.
        """

        def failure_share(rank_difference: int) -> int:
            chart = ResultChart.get_chart_for_difference(rank_difference)
            rows = ResultChartOutcome.objects.filter(chart=chart).select_related("outcome")
            return sum(
                row.max_roll - row.min_roll + 1 for row in rows if row.outcome.success_level < 0
            )

        def success_share(rank_difference: int) -> int:
            chart = ResultChart.get_chart_for_difference(rank_difference)
            rows = ResultChartOutcome.objects.filter(chart=chart).select_related("outcome")
            return sum(
                row.max_roll - row.min_roll + 1 for row in rows if row.outcome.success_level > 0
            )

        self.assertGreaterEqual(failure_share(-5), failure_share(-2))
        self.assertLess(success_share(-5), success_share(-2))
        # Never a dead end: a hopeless matchup still produces a non-failure outcome.
        self.assertGreater(100 - failure_share(-5), 0)

    def test_hopeless_matchup_is_not_reported_impossible(self):
        """The chip charts -5 and -6 keep their Success outcome (#2707, #4551 decision 5).

        chart_has_success_outcomes(rank_difference) feeds
        world.mechanics.services._get_difficulty_indicator_for_check, which maps False to
        DifficultyIndicator.IMPOSSIBLE. Charts -6 (1% Success) and -5 (5%) stay winnable so
        a party far above its level chips away. Charts -7 and -8 are the impossible ones
        (see ImpossibleChartTests); the approach is listed labelled Impossible, not dropped.
        """
        for rank_difference in (-5, -6):
            with self.subTest(rank_difference=rank_difference):
                self.assertTrue(chart_has_success_outcomes(rank_difference))

    def test_botch_bands_present_only_on_negative_charts(self):
        """Critical Failure bands exist at rank_diff -1 through -8, not at 0+."""
        botch_outcome = CheckOutcome.objects.get(name="Critical Failure")
        for rank_diff in range(-8, 0):
            chart = ResultChart.get_chart_for_difference(rank_diff)
            assert chart is not None
            has_botch = ResultChartOutcome.objects.filter(
                chart=chart, outcome=botch_outcome
            ).exists()
            self.assertTrue(
                has_botch,
                f"Chart at rank_diff={rank_diff} should have a Critical Failure band",
            )
        for rank_diff in range(7):
            chart = ResultChart.get_chart_for_difference(rank_diff)
            assert chart is not None
            has_botch = ResultChartOutcome.objects.filter(
                chart=chart, outcome=botch_outcome
            ).exists()
            self.assertFalse(
                has_botch,
                f"Chart at rank_diff={rank_diff} should NOT have a Critical Failure band",
            )

    def test_botch_share_monotonically_non_increasing(self):
        """Botch share decays from the worst chart (20%) to EVEN (0%)."""
        botch_outcome = CheckOutcome.objects.get(name="Critical Failure")

        def botch_share(rank_difference: int) -> int:
            chart = ResultChart.get_chart_for_difference(rank_difference)
            rows = ResultChartOutcome.objects.filter(chart=chart, outcome=botch_outcome)
            return sum(row.max_roll - row.min_roll + 1 for row in rows)

        shares = [botch_share(rd) for rd in range(-8, 1)]
        self.assertEqual(shares, sorted(shares, reverse=True))
        # Even footing and above: zero botch
        self.assertEqual(botch_share(0), 0)

    def test_all_charts_have_distinct_bands(self):
        """No two rank_differences share the same set of outcome bands (#2760).

        Today -4/-3 share identical bands, +1/+2 share, +3/+4 share, +5/+6 share.
        After this change every chart must have distinct bands.
        """
        band_signatures: dict[frozenset, int] = {}
        for rank_diff in range(-8, 7):
            chart = ResultChart.get_chart_for_difference(rank_diff)
            assert chart is not None
            rows = ResultChartOutcome.objects.filter(chart=chart).select_related("outcome")
            sig = frozenset((row.outcome.name, row.min_roll, row.max_roll) for row in rows)
            self.assertNotIn(
                sig,
                band_signatures,
                f"Chart at rank_diff={rank_diff} duplicates rank_diff={band_signatures.get(sig)}",
            )
            band_signatures[sig] = rank_diff

    def test_partial_success_gradient(self):
        """Partial Success bands exist on charts from -7 through +5, not on -8 or +6."""
        partial_outcome = CheckOutcome.objects.get(name="Partial Success")
        for rank_diff in range(-7, 6):
            chart = ResultChart.get_chart_for_difference(rank_diff)
            assert chart is not None
            has_partial = ResultChartOutcome.objects.filter(
                chart=chart, outcome=partial_outcome
            ).exists()
            self.assertTrue(
                has_partial,
                f"Chart at rank_diff={rank_diff} should have a Partial Success band",
            )
        # +6 (Inevitable) has no Partial — pure win
        chart = ResultChart.get_chart_for_difference(6)
        assert chart is not None
        has_partial = ResultChartOutcome.objects.filter(
            chart=chart, outcome=partial_outcome
        ).exists()
        self.assertFalse(
            has_partial,
            "Chart at rank_diff=+6 should NOT have a Partial Success band",
        )


_TIERS = (-2, -1, 0, 1, 2)
_DEEPEST = -8
_HIGHEST = 6


def _band_share(rank_difference: int, success_level: int) -> int:
    """Rolls (out of 100) landing on exactly this success level on the chart."""
    chart = ResultChart.get_chart_for_difference(rank_difference)
    assert chart is not None
    rows = ResultChartOutcome.objects.filter(chart=chart, outcome__success_level=success_level)
    return sum(row.max_roll - row.min_roll + 1 for row in rows)


def _at_least(rank_difference: int, success_level: int) -> int:
    """Rolls (out of 100) landing on this success level or better."""
    return sum(_band_share(rank_difference, level) for level in _TIERS if level >= success_level)


class ImpossibleChartTests(TestCase):
    """Monotonic charts and the impossible zone (#4593, #4551 section 5.6)."""

    def setUp(self):
        seed_check_resolution_tables()
        ResultChart.clear_cache()

    def test_every_at_least_chance_is_non_decreasing_across_differences(self):
        """No tier-or-better chance falls as the rank difference rises, -8 to +6."""
        for level in (-1, 0, 1, 2):
            chances = [_at_least(rd, level) for rd in range(_DEEPEST, _HIGHEST + 1)]
            with self.subTest(at_least=level):
                self.assertEqual(chances, sorted(chances), chances)

    def test_every_chart_covers_the_whole_d100(self):
        for rd in range(_DEEPEST, _HIGHEST + 1):
            total = sum(_band_share(rd, level) for level in _TIERS)
            with self.subTest(rank_difference=rd):
                self.assertEqual(total, 100)

    def test_charts_minus_seven_and_eight_have_no_success(self):
        for rd in (-7, -8):
            with self.subTest(rank_difference=rd):
                self.assertEqual(_at_least(rd, 1), 0)
                self.assertFalse(chart_has_success_outcomes(rd))

    def test_minus_seven_keeps_partial_success_and_minus_eight_only_fails(self):
        self.assertGreater(_band_share(-7, 0), 0)
        self.assertEqual(_at_least(-8, 0), 0)
        self.assertGreater(_band_share(-8, -1), 0)

    def test_chart_minus_seven_and_eight_odds_stay_at_or_below_minus_six(self):
        for rd in (-7, -8):
            for level in (-1, 0, 1, 2):
                with self.subTest(rank_difference=rd, at_least=level):
                    self.assertLessEqual(_at_least(rd, level), _at_least(-6, level))

    def test_no_impossible_chart_sits_above_a_winnable_one(self):
        winnable = [chart_has_success_outcomes(rd) for rd in range(_DEEPEST, _HIGHEST + 1)]
        self.assertEqual(winnable, sorted(winnable))

    def test_placeholder_names_for_the_deep_charts(self):
        self.assertEqual(ResultChart.objects.get(rank_difference=-7).name, "Failure -7")
        self.assertEqual(ResultChart.objects.get(rank_difference=-8).name, "Impossible")

    def test_below_minus_eight_resolves_to_the_impossible_chart(self):
        """No clamp is needed: the closest-chart fallback lands on -8 (was the -50 case)."""
        for rank_difference in (-9, -50):
            with self.subTest(rank_difference=rank_difference):
                chart = ResultChart.get_chart_for_difference(rank_difference)
                assert chart is not None
                self.assertEqual(chart.rank_difference, -8)
                self.assertFalse(chart_has_success_outcomes(rank_difference))

    def test_chip_charts_keep_their_success_chance(self):
        self.assertEqual(_band_share(-6, 1), 1)
        self.assertEqual(_band_share(-5, 1), 5)
