"""Band positions and the slide (#4601, slice b of #4551; the pin removed in #4723).

Against the seeded rank ladder (0/10/25/50/80/115/155/200/250) and result charts.
"""

from django.test import TestCase

from world.checks.slide import band_position, resolve_standing, slide_chart
from world.seeds.checks import seed_check_resolution_tables
from world.traits.models import ResultChart, ResultChartOutcome

_TIERS = (-2, -1, 0, 1, 2)


def _slid(difference: int, share: float):
    chart = ResultChart.get_chart_for_difference(difference)
    toward = ResultChart.get_chart_for_difference(difference + 1)
    rows = list(
        ResultChartOutcome.objects.filter(chart__in=[chart, toward]).select_related("outcome")
    )
    return slide_chart(chart, toward, share, rows)


def _odds(slid) -> dict[int, float]:
    return {
        level: round(sum(b.probability for b in slid.bands if b.outcome.success_level == level), 4)
        for level in _TIERS
    }


class SlideTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_check_resolution_tables()

    def setUp(self):
        ResultChart.clear_cache()


class BandPositionTests(SlideTestBase):
    def test_a_total_sits_part_way_through_its_band(self):
        position = band_position(40)
        self.assertEqual(position.rank.rank, 2)
        self.assertAlmostEqual(position.share, 0.6)
        self.assertEqual(position.text, "Competent (rank 2), 60% toward Expert (rank 3)")

    def test_a_threshold_total_shows_the_bare_rank(self):
        self.assertEqual(band_position(50).text, "Expert (rank 3)")

    def test_the_top_rank_has_no_next_rank(self):
        position = band_position(400)
        self.assertEqual(position.rank.rank, 8)
        self.assertEqual(position.share, 0.0)
        self.assertEqual(position.text, "Mythic (rank 8)")


class SlideTests(SlideTestBase):
    def test_no_slide_reproduces_the_authored_chart(self):
        for difference in range(-8, 7):
            chart = ResultChart.get_chart_for_difference(difference)
            authored = dict.fromkeys(_TIERS, 0)
            for row in ResultChartOutcome.objects.filter(chart=chart).select_related("outcome"):
                authored[row.outcome.success_level] += (row.max_roll - row.min_roll + 1) / 100
            with self.subTest(difference=difference):
                self.assertEqual(_odds(_slid(difference, 0.0)), authored)

    def test_halfway_through_the_band_gets_the_halfway_odds(self):
        """Chart -1 sliding toward 0: Success or better 22%, 31%, 40%; no Crit yet."""
        for share, expected in ((0.0, 0.22), (0.5, 0.31), (1.0, 0.40)):
            slid = _slid(-1, share)
            with self.subTest(share=share):
                self.assertAlmostEqual(slid.at_least(1), expected)
                self.assertEqual(slid.at_least(2), 0)

    def test_minus_seven_slides_toward_partial_success_and_never_success(self):
        """The next chart's Success (1) counts as Partial Success (0) on -7."""
        odds = _odds(_slid(-7, 1.0))
        self.assertEqual(odds[-2], 0.10)
        self.assertEqual(odds[-1], 0.79)
        self.assertEqual(odds[0], 0.11)
        self.assertEqual(odds[1], 0)

    def test_minus_eight_only_turns_botches_into_failures(self):
        odds = _odds(_slid(-8, 1.0))
        self.assertEqual(odds[-2], 0.15)
        self.assertEqual(odds[-1], 0.85)
        self.assertEqual(odds[0], 0)

    def test_every_at_least_chance_rises_through_every_band(self):
        """The guard: from -8 to +6 in quarter bands, no "at least X" chance ever falls."""
        for level in (-1, 0, 1, 2):
            chances = [
                round(_slid(difference, share / 4).at_least(level), 6)
                for difference in range(-8, 6)
                for share in range(4)
            ]
            with self.subTest(at_least=level):
                self.assertEqual(chances, sorted(chances))


class StandingTests(SlideTestBase):
    def test_a_check_halfway_through_a_band_slides_halfway(self):
        # Roller 37.5 points: Competent (rank 2), 50% toward Expert; target Expert (50).
        standing = resolve_standing(37, 50)
        self.assertEqual(standing.chart_difference, -1)
        self.assertAlmostEqual(standing.share, 12 / 25)

    def test_one_buff_moves_the_odds_inside_a_band(self):
        plain = resolve_standing(30, 50)
        buffed = resolve_standing(36, 50)
        self.assertEqual(plain.chart_difference, buffed.chart_difference)
        self.assertGreater(buffed.slid.at_least(1), plain.slid.at_least(1))

    def test_a_pile_of_buffs_lifts_a_check_off_an_impossible_chart(self):
        """#4723: modifiers count in full, so a big enough pile reaches a winnable chart."""
        # Unbuffed: Novice (rank 1), 67% through, against Mythic (rank 8): -6.33, chart -7.
        plain = resolve_standing(20, 250)
        self.assertEqual(plain.chart_difference, -7)
        self.assertEqual(plain.slid.at_least(1), 0)
        # +120 points: Grandmaster (rank 5), 62.5% through: -2.375, chart -3 slid 62.5%.
        buffed = resolve_standing(20 + 120, 250)
        self.assertEqual(buffed.chart_difference, -3)
        self.assertAlmostEqual(buffed.share, 0.625)
        self.assertGreater(buffed.slid.at_least(1), 0)

    def test_modifiers_on_the_target_count_in_full(self):
        """A heavily debuffed opponent is rolled against at its debuffed total."""
        standing = resolve_standing(20, 120)
        self.assertEqual(standing.chart_difference, -4)
        self.assertGreater(standing.slid.at_least(1), 0)

    def test_buffs_count_in_full_at_a_three_rank_gap(self):
        plain = resolve_standing(20, 80)
        buffed = resolve_standing(120, 80)
        self.assertGreater(buffed.slid.at_least(1), plain.slid.at_least(1) + 0.3)

    def test_below_the_lowest_chart_sits_at_the_bottom_of_its_band(self):
        standing = resolve_standing(0, 10_000)
        self.assertEqual(standing.chart_difference, -8)
        self.assertEqual(standing.share, 0.0)

    def test_a_small_buff_slides_within_the_impossible_chart(self):
        # Incompetent (rank 0) against Mythic (rank 8) is -8.0. +5 points: -7.5.
        standing = resolve_standing(5, 250)
        self.assertEqual(standing.chart_difference, -8)
        self.assertAlmostEqual(standing.share, 0.5)

    def test_a_total_below_the_lowest_chart_never_slides(self):
        """A total still below the lowest chart gives that chart's own odds, never a slide
        (review finding on #4604)."""
        ResultChart.objects.filter(rank_difference=-8).delete()
        ResultChart.clear_cache()
        # -7.5 is below the lowest chart (-7) once chart -8 is gone.
        standing = resolve_standing(5, 250)
        self.assertEqual(standing.chart_difference, -7)
        self.assertEqual(standing.share, 0.0)
