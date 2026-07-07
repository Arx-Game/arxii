from django.db.models import Model
from django.test import TestCase

from world.seeds.clusters import CLUSTER_SEEDERS, seeded_models


class TestClusterRegistry(TestCase):
    def test_expected_clusters_registered(self) -> None:
        self.assertEqual(
            set(CLUSTER_SEEDERS),
            {
                "checks",
                "combat_checks",
                "social",
                "investigation",
                "social_relationships",
                "social_actions",
                "magic",
                "items",
                "combat",
                "battles",
                "consent",
                "character_creation",
                "justice",
                "governance",
                "scandal",
                "domain_dev",
                "stealth",
                "perception",
                "civic_hubs",
                "building_condition",
                "kudos",
                "gm",
            },
        )

    def test_character_creation_cluster_registered_after_magic(self) -> None:
        keys = list(CLUSTER_SEEDERS)
        assert "character_creation" in keys
        self.assertLess(keys.index("magic"), keys.index("character_creation"))

    def test_seeded_models_are_model_classes(self) -> None:
        models = seeded_models()
        self.assertTrue(models)
        self.assertTrue(all(issubclass(m, Model) for m in models))

    def test_character_creation_cluster_is_idempotent_no_op_on_second_run(self) -> None:
        from world.seeds.database import seed_dev_database

        seed_dev_database()  # first run creates
        report = seed_dev_database()  # second run creates nothing new
        self.assertEqual(report.clusters["character_creation"], 0)

    def test_seeded_models_by_cluster_groups_per_cluster(self) -> None:
        from world.seeds.clusters import seeded_models, seeded_models_by_cluster

        grouped = seeded_models_by_cluster()
        # every registered cluster has an entry
        self.assertEqual(set(grouped), set(CLUSTER_SEEDERS))
        self.assertIn("character_creation", grouped)
        self.assertGreaterEqual(len(grouped["character_creation"]), 1)
        # the flat-list contract is independent and unchanged
        flat = seeded_models()
        self.assertTrue(all(issubclass(m, Model) for m in flat))
