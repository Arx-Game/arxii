"""Tests for check-success analytics (#1221 Task 2).

Covers the pure probability math in `checks_analytics.py` (mirrors the check
engine's roll math exactly — see `world.checks.services.perform_check`) plus a
thin integration test for the fragment view that renders it.
"""

from __future__ import annotations

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from web.admin.tuning.checks_analytics import compute_chart_distributions, compute_matchup
from world.traits.factories import (
    CheckOutcomeFactory,
    CheckRankFactory,
    ResultChartFactory,
    ResultChartOutcomeFactory,
)
from world.traits.models import ResultChart


class ComputeChartDistributionsTests(TestCase):
    """Tally correctness for `compute_chart_distributions` / `compute_matchup`."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Two-band chart (rank_difference=0): clean 50/50 split makes the
        # roll_modifier-shift and clamping math easy to hand-verify.
        cls.failure = CheckOutcomeFactory(name="Failure", success_level=-1)
        cls.success = CheckOutcomeFactory(name="Success", success_level=1)
        cls.chart_even = ResultChartFactory(rank_difference=0, name="Even")
        ResultChartOutcomeFactory(
            chart=cls.chart_even, outcome=cls.failure, min_roll=1, max_roll=50
        )
        ResultChartOutcomeFactory(
            chart=cls.chart_even, outcome=cls.success, min_roll=51, max_roll=100
        )

        # Three-band chart (rank_difference=1) for the sum-to-1 and
        # pool-into-top-band (clamping) tests.
        cls.partial = CheckOutcomeFactory(name="Partial Success", success_level=0)
        cls.chart_hard = ResultChartFactory(rank_difference=1, name="Hard")
        ResultChartOutcomeFactory(
            chart=cls.chart_hard, outcome=cls.failure, min_roll=1, max_roll=40
        )
        ResultChartOutcomeFactory(
            chart=cls.chart_hard, outcome=cls.partial, min_roll=41, max_roll=60
        )
        ResultChartOutcomeFactory(
            chart=cls.chart_hard, outcome=cls.success, min_roll=61, max_roll=100
        )

    def setUp(self) -> None:
        # The ResultChart chart-lookup cache is a class-level dict, not
        # transaction-scoped — clear it so each test sees this test's rows.
        ResultChart.clear_cache()

    def test_probabilities_sum_to_one_per_chart(self) -> None:
        distributions = compute_chart_distributions(roll_modifier=0)
        assert len(distributions) == 2
        for dist in distributions:
            total = sum(band.probability for band in dist.bands)
            self.assertAlmostEqual(total, 1.0, places=9)

    def test_baseline_even_chart_is_a_true_fifty_fifty_split(self) -> None:
        distributions = compute_chart_distributions(roll_modifier=0)
        even = next(d for d in distributions if d.rank_difference == 0)
        by_name = {b.name: b.probability for b in even.bands}
        self.assertAlmostEqual(by_name["Failure"], 0.5, places=9)
        self.assertAlmostEqual(by_name["Success"], 0.5, places=9)
        self.assertAlmostEqual(even.success_probability, 0.5, places=9)

    def test_positive_roll_modifier_shifts_mass_toward_higher_success_level(self) -> None:
        baseline = next(
            d for d in compute_chart_distributions(roll_modifier=0) if d.rank_difference == 0
        )
        shifted = next(
            d for d in compute_chart_distributions(roll_modifier=10) if d.rank_difference == 0
        )

        baseline_success = next(b.probability for b in baseline.bands if b.name == "Success")
        shifted_success = next(b.probability for b in shifted.bands if b.name == "Success")

        assert shifted_success > baseline_success
        assert shifted.success_probability > baseline.success_probability
        # Hand-verified: rolls 1-40 -> effective 11-50 (Failure); rolls 41-100
        # -> effective 51-100 (Success, including the 10 rolls clamped to 100).
        self.assertAlmostEqual(shifted_success, 0.60, places=9)

    def test_clamping_at_100_pools_mass_into_the_top_band(self) -> None:
        # A modifier this large drives every roll's effective value to the
        # clamp ceiling of 100, so all 100 rolls collapse into whichever
        # band covers roll 100 — the highest success_level band.
        distributions = compute_chart_distributions(roll_modifier=200)
        hard = next(d for d in distributions if d.rank_difference == 1)

        assert len(hard.bands) == 1
        assert hard.bands[0].name == "Success"
        self.assertAlmostEqual(hard.bands[0].probability, 1.0, places=9)
        self.assertAlmostEqual(hard.success_probability, 1.0, places=9)

    def test_bands_ordered_by_success_level_descending(self) -> None:
        distributions = compute_chart_distributions(roll_modifier=0)
        hard = next(d for d in distributions if d.rank_difference == 1)
        levels = [b.success_level for b in hard.bands]
        assert levels == sorted(levels, reverse=True)

    def test_matchup_with_unseeded_ranks_returns_the_rank_difference_zero_chart(self) -> None:
        # No CheckRank rows exist anywhere in this test module, so both the
        # roller and target rank lookups miss and default the difference to 0
        # (mirroring `_compute_check_breakdown`).
        matchup = compute_matchup(roller_points=999, target_difficulty=5, roll_modifier=0)

        assert matchup is not None
        assert matchup.rank_difference == 0
        assert matchup.chart_name == self.chart_even.name

    def test_matchup_with_seeded_ranks_derives_nonzero_rank_difference(self) -> None:
        CheckRankFactory(rank=0, min_points=0, name="Incompetent")
        CheckRankFactory(rank=1, min_points=10, name="Novice")

        # roller has 10+ points (rank 1), target difficulty is 0 (rank 0) ->
        # rank_difference = 1.
        matchup = compute_matchup(roller_points=15, target_difficulty=0, roll_modifier=0)

        assert matchup is not None
        assert matchup.rank_difference == 1
        assert matchup.chart_name == self.chart_hard.name

    def test_matchup_fallback_chart_reports_derived_rank_difference_not_charts_own(
        self,
    ) -> None:
        # No chart is seeded at rank_difference exactly +1, so
        # `ResultChart.get_chart_for_difference` falls back to the nearest
        # seeded chart. `chart_hard` (rank_difference=1) from setUpTestData
        # would make this fallback invisible, so build a fresh, isolated set
        # of charts: only -2 and +2 exist, and the matchup derives +1 -> the
        # nearer chart (+2) is selected. The returned rank_difference must be
        # the *derived* 1, not the fallback chart's own field value of 2.
        ResultChart.objects.all().delete()
        ResultChart.clear_cache()
        minus_two = ResultChartFactory(rank_difference=-2, name="Minus2")
        plus_two = ResultChartFactory(rank_difference=2, name="Plus2")
        for chart in (minus_two, plus_two):
            ResultChartOutcomeFactory(chart=chart, outcome=self.failure, min_roll=1, max_roll=50)
            ResultChartOutcomeFactory(chart=chart, outcome=self.success, min_roll=51, max_roll=100)

        CheckRankFactory(rank=0, min_points=0, name="Incompetent")
        CheckRankFactory(rank=1, min_points=10, name="Novice")

        # roller rank 1, target rank 0 -> derived rank_difference = 1, which
        # has no exact chart -> falls back to the nearer chart, +2 (distance 1
        # vs. distance 3 for -2).
        matchup = compute_matchup(roller_points=15, target_difficulty=0, roll_modifier=0)

        assert matchup is not None
        assert matchup.rank_difference == 1
        assert matchup.chart_name == plus_two.name


class ComputeMatchupNoChartsTests(TestCase):
    """No ResultChart rows exist at all — the lookup has nothing to return."""

    def setUp(self) -> None:
        ResultChart.clear_cache()

    def test_matchup_returns_none_when_no_charts_exist(self) -> None:
        assert compute_matchup(roller_points=0, target_difficulty=0) is None


class TuningChecksFragmentViewTests(TestCase):
    """Integration test for the real `admin_tuning_checks` fragment view."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser(
            "rootadmin2", "root2@example.com", "pw-123456"
        )
        cls.staff = AccountDB.objects.create_user("staffer2", "s2@example.com", "pw-123456")
        cls.staff.is_staff = True
        cls.staff.save()

        failure = CheckOutcomeFactory(name="Failure", success_level=-1)
        success = CheckOutcomeFactory(name="Success", success_level=1)
        chart = ResultChartFactory(rank_difference=0, name="Even")
        ResultChartOutcomeFactory(chart=chart, outcome=failure, min_roll=1, max_roll=50)
        ResultChartOutcomeFactory(chart=chart, outcome=success, min_roll=51, max_roll=100)

    def setUp(self) -> None:
        ResultChart.clear_cache()

    def test_staff_non_superuser_forbidden(self) -> None:
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_tuning_checks"))
        self.assertEqual(resp.status_code, 403)

    def test_superuser_sees_rendered_analytics_table(self) -> None:
        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_tuning_checks"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        assert "Even" in body
        # Unambiguous check on the table's success-probability cell: the chart
        # is a clean 50/50 split, so the true percentage is "50%". Before the
        # fix, the 0.0-1.0 fraction was piped through floatformat:1 directly
        # (`{{ dist.success_probability|floatformat:1 }}%`), rendering "0.5%"
        # for this exact chart — that string would fail this assertion.
        assert '<td class="success-probability-cell">50%</td>' in body
        assert "0.5%" not in body
        assert 'name="roll_modifier"' in body
        assert 'name="roller_points"' in body
        assert 'name="target_difficulty"' in body

    def test_query_params_drive_the_matchup_sub_form(self) -> None:
        self.client.force_login(self.super)
        resp = self.client.get(
            reverse("admin_tuning_checks"),
            {"roll_modifier": "10", "roller_points": "5", "target_difficulty": "0"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        assert "Even" in body
