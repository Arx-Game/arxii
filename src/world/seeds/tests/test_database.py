import os
from unittest import mock

from django.test import TestCase

from core_management.content_fixtures import ContentError
from world.seeds.clusters import seeded_models
from world.seeds.database import seed_dev_database
from world.seeds.tests.content_stub import STUB_TRAIT_NAME, stub_content_root
from world.seeds.types import SeedReport
from world.traits.models import Trait


class TestSeedDevDatabase(TestCase):
    @stub_content_root()
    def test_returns_seed_report_with_clusters(self) -> None:
        report = seed_dev_database()
        self.assertIsInstance(report, SeedReport)
        # every registered cluster reports a count (>= 0)
        self.assertIn("magic", report.clusters)
        self.assertIn("items", report.clusters)
        self.assertEqual(report.created_total, sum(report.clusters.values()))

    @stub_content_root()
    def test_loads_content_repo_before_seeding_clusters(self) -> None:
        """The stub content root's Trait lands in the DB and is reported (#2474)."""
        report = seed_dev_database()
        self.assertIn("content", report.clusters)
        self.assertGreater(report.clusters["content"], 0)
        self.assertTrue(Trait.objects.filter(name=STUB_TRAIT_NAME).exists())

    def test_missing_content_repo_raises_loudly_before_any_cluster_seeds(self) -> None:
        """Decision 5 (#2474): no silent skip, no synthetic fallback.

        Asserting zero cluster-tracked rows exist after the raise proves the
        content load runs BEFORE any cluster seeder, not merely that it fails
        at some point during the call.
        """
        with mock.patch.dict("os.environ", {}, clear=False):
            os.environ.pop("CONTENT_REPO_PATH", None)
            with self.assertRaises(ContentError) as ctx:
                seed_dev_database()
        self.assertIn("CONTENT_REPO_PATH", str(ctx.exception))
        self.assertEqual(sum(m.objects.count() for m in seeded_models()), 0)
