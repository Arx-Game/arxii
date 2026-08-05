"""The boundaries seed cluster populates the starter ContentTheme catalog (#3004)."""

from django.test import TestCase

from world.boundaries.models import ContentTheme
from world.seeds.clusters import CLUSTER_SEEDERS


class BoundariesClusterTests(TestCase):
    def test_cluster_is_registered(self) -> None:
        assert "boundaries" in CLUSTER_SEEDERS

    def test_seeds_the_starter_themes(self) -> None:
        CLUSTER_SEEDERS["boundaries"]()
        assert ContentTheme.objects.count() == 4
        assert set(ContentTheme.objects.values_list("key", flat=True)) == {
            "child-endangerment",
            "suicide-self-harm",
            "sexual-violence",
            "torture",
        }

    def test_is_idempotent(self) -> None:
        CLUSTER_SEEDERS["boundaries"]()
        CLUSTER_SEEDERS["boundaries"]()
        assert ContentTheme.objects.count() == 4
