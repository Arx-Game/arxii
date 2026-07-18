import os
from unittest import mock

from django.test import TestCase

from core_management.content_fixtures import ContentError
from world.magic.models import Technique
from world.magic.seeds_cast import TECHNIQUE_CAST_TEMPLATE_NAME
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

    @stub_content_root()
    def test_technique_action_template_fk_resolves_on_first_run(self) -> None:
        """First-run ordering gap (#2474): config prerequisites precede content load.

        The stub's lore-repo-shaped Technique fixtures FK the shared "Technique
        Cast" ActionTemplate by natural key, exactly like real lore-repo
        Technique fixtures do. On a fresh database, that ActionTemplate is
        pure config seeded by ``ensure_technique_cast_content()`` — which used
        to run only later, inside the cluster-seeder loop, AFTER the content
        load. Before the fix, ``load_world_content()``'s deferred-retry loop
        could never resolve this FK (the config row it waits on is never
        created by the content/grid load itself), so every Technique row was
        silently skipped on the very first run. Asserting a stub Technique
        exists with its action_template correctly wired proves the ordering
        fix, not just that seeding didn't raise.
        """
        seed_dev_database()
        technique = Technique.objects.filter(name="Burning Strike").first()
        self.assertIsNotNone(technique)
        self.assertIsNotNone(technique.action_template)
        self.assertEqual(technique.action_template.name, TECHNIQUE_CAST_TEMPLATE_NAME)

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
