from django.db.models import Model
from django.test import TestCase

from world.seeds.clusters import CLUSTER_SEEDERS, seeded_models
from world.seeds.tests.content_stub import stub_content_root


class TestClusterRegistry(TestCase):
    def test_expected_clusters_registered(self) -> None:
        self.assertEqual(
            set(CLUSTER_SEEDERS),
            {
                "checks",
                "combat_checks",
                "social",
                "investigation",
                "worship",
                "social_relationships",
                "relationship_scale",
                "social_actions",
                "social_combat",
                "magic",
                "items",
                "combat",
                "battles",
                "consent",
                "character_creation",
                "missions",
                "tutorial",
                "progression",
                "npc_services",
                "justice",
                "governance",
                "scandal",
                "domain_dev",
                "stealth",
                "security",
                "perception",
                "civic_hubs",
                "counterplay",
                "building_condition",
                "property_grants",
                "kudos",
                "survivability",
                "market",
                "gm",
                "kinship",
                "houses",
                "covenant_roles",
                "propaganda",
                "skills",
                "project_resonance",
                "roster",
                "agriculture",
                "traits",
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

    @stub_content_root()
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

    def test_cg_explanations_seeded_and_nonempty(self) -> None:
        from world.character_creation.models import CGExplanation
        from world.seeds.character_creation import (
            CG_EXPLANATION_COPY,
            seed_character_creation_dev,
        )

        seed_character_creation_dev()
        for key in CG_EXPLANATION_COPY:
            row = CGExplanation.objects.get(key=key)
            self.assertTrue(row.text.strip(), f"blank copy for {key}")
        # idempotent + updates edited copy
        CGExplanation.objects.filter(key="origin_heading").update(text="stale")
        seed_character_creation_dev()
        self.assertNotEqual(CGExplanation.objects.get(key="origin_heading").text, "stale")

    def test_every_active_beginning_has_a_seeded_tradition(self) -> None:
        """Seed-integrity regression net (#2426 whole-branch-review finding).

        Without ``seed_beginning_traditions()``, no ``BeginningTradition`` rows
        exist on a fresh Big-Button-only DB, so the CG Tradition step is empty
        for every Beginning — CG is uncompletable. Runs the full Big Button
        (not just the ``character_creation`` cluster in isolation) since the
        seeder depends on the "Unbound" Tradition row existing first — real
        lore-repo content, loaded via ``load_world_content()`` (#2474); the
        stub content root carries an equivalent-shaped stand-in.
        """
        from world.character_creation.models import Beginnings
        from world.seeds.database import seed_dev_database

        with stub_content_root():
            seed_dev_database()

        beginnings = Beginnings.objects.filter(is_active=True)
        self.assertTrue(beginnings.exists(), "expected at least one active seeded Beginning")
        for beginning in beginnings:
            self.assertTrue(
                beginning.beginning_traditions.exists(),
                f"{beginning.name!r} has no seeded BeginningTradition row (#2426)",
            )
