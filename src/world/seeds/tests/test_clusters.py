from django.db.models import Model
from django.test import TestCase

from world.seeds.clusters import CLUSTER_SEEDERS, seeded_models


class TestClusterRegistry(TestCase):
    def test_expected_clusters_registered(self) -> None:
        self.assertEqual(set(CLUSTER_SEEDERS), {"magic", "items", "combat", "checks"})

    def test_seeded_models_are_model_classes(self) -> None:
        models = seeded_models()
        self.assertTrue(models)
        self.assertTrue(all(issubclass(m, Model) for m in models))
