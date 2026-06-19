from django.test import TestCase

from world.seeds.database import seed_dev_database
from world.seeds.types import SeedReport


class TestSeedDevDatabase(TestCase):
    def test_returns_seed_report_with_clusters(self) -> None:
        report = seed_dev_database()
        self.assertIsInstance(report, SeedReport)
        # every registered cluster reports a count (>= 0)
        self.assertIn("magic", report.clusters)
        self.assertIn("items", report.clusters)
        self.assertEqual(report.created_total, sum(report.clusters.values()))
