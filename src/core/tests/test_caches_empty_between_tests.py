"""The per-test flush empties project caches between tests (#3657 tranche 1).

``ResultChart.get_chart_for_difference`` fills a class-level cache from the table
on first use and never refills it. Before ``core.testing`` registered its flusher,
the charts one test built answered every later check in the process after their
rows were rolled back. Django runs a class's tests in name order, so the first
test here fills the cache and the second asserts it starts empty.
"""

from django.test import TestCase

from world.traits.factories import CheckSystemSetupFactory
from world.traits.models import ResultChart


class ResultChartCacheIsEmptyAtTestStart(TestCase):
    def test_1_a_check_fills_the_chart_cache(self) -> None:
        CheckSystemSetupFactory.create()
        chart = ResultChart.get_chart_for_difference(0)
        self.assertIsNotNone(chart)
        self.assertIn(0, ResultChart._chart_cache)

    def test_2_the_next_test_starts_with_no_cached_chart(self) -> None:
        self.assertEqual(ResultChart._chart_cache, {})
        CheckSystemSetupFactory.create()
        chart = ResultChart.get_chart_for_difference(0)
        self.assertEqual(ResultChart.objects.get(pk=chart.pk).rank_difference, 0)
