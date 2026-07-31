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

    def test_deep_gap_degrades_effect_without_increasing_failure(self):
        """Past a two-rung gap, the failure share must stop growing (#2707).

        A party attacking something far above its level should chip away, not
        whiff for ten rounds. What degrades with depth is what you accomplish.
        """
        seed_check_resolution_tables()
        ResultChart.clear_cache()

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

        self.assertLess(failure_share(-5), failure_share(-2))
        self.assertLess(success_share(-5), success_share(-2))
        # Never a dead end: a hopeless matchup still produces a non-failure outcome.
        self.assertGreater(100 - failure_share(-5), 0)

    def test_hopeless_matchup_is_not_reported_impossible(self):
        """A hopeless matchup must still be offered as an available action (#2707 review).

        chart_has_success_outcomes(rank_difference) feeds
        world.mechanics.services._get_difficulty_indicator_for_check, which maps False to
        DifficultyIndicator.IMPOSSIBLE -- and both approach-listing call sites drop the
        approach from the player's available-actions list entirely when that indicator
        comes back. Every rank_difference <= -5 snaps to the HOPELESS chart (the most
        extreme charts, -6 and -5, share one chart via get_chart_for_difference's
        closest-match fallback), so the deepest gap in the ladder must still carry a
        success_level > 0 outcome -- chipping, never vanishing from the list.
        """
        for rank_difference in (-5, -6, -50):
            with self.subTest(rank_difference=rank_difference):
                self.assertTrue(chart_has_success_outcomes(rank_difference))

    def test_botch_bands_present_only_on_negative_charts(self):
        """Critical Failure bands exist at rank_diff -1 through -6, not at 0+."""
        botch_outcome = CheckOutcome.objects.get(name="Critical Failure")
        for rank_diff in range(-6, 0):
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
        """Botch share decays from worst chart to EVEN (10% -> 7% -> 5% -> 3% -> 2% -> 2% -> 0%)."""
        botch_outcome = CheckOutcome.objects.get(name="Critical Failure")

        def botch_share(rank_difference: int) -> int:
            chart = ResultChart.get_chart_for_difference(rank_difference)
            rows = ResultChartOutcome.objects.filter(chart=chart, outcome=botch_outcome)
            return sum(row.max_roll - row.min_roll + 1 for row in rows)

        shares = [botch_share(rd) for rd in range(-6, 1)]
        self.assertEqual(shares, sorted(shares, reverse=True))
        # Even footing and above: zero botch
        self.assertEqual(botch_share(0), 0)

    def test_all_charts_have_distinct_bands(self):
        """No two rank_differences share the same set of outcome bands (#2760).

        Today -4/-3 share identical bands, +1/+2 share, +3/+4 share, +5/+6 share.
        After this change every chart must have distinct bands.
        """
        band_signatures: dict[frozenset, int] = {}
        for rank_diff in range(-6, 7):
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
        """Partial Success bands exist on charts from -6 through +5, not on +6."""
        partial_outcome = CheckOutcome.objects.get(name="Partial Success")
        for rank_diff in range(-6, 6):
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
