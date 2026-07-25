"""Guard: the result-chart ladder must never invert again (#2707).

`rank_difference = roller_rank - target_rank`, so a POSITIVE difference means
the roller is stronger and must select an EASIER chart. This inverted silently
for the whole life of the project because nothing asserted direction.
"""

from django.test import TestCase

from world.seeds.checks import seed_check_resolution_tables
from world.traits.models import CheckRank, ResultChart, ResultChartOutcome


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
