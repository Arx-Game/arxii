from django.test import TestCase

from world.magic.constants import AFFINITY_ABYSSAL, AFFINITY_CELESTIAL, AFFINITY_PRIMAL
from world.magic.exceptions import AffinityNotConfigured
from world.magic.factories import AffinityFactory
from world.magic.models import Affinity


class AffinityGetterTests(TestCase):
    def setUp(self) -> None:
        Affinity.objects.clear_cache()
        super().setUp()

    def tearDown(self) -> None:
        Affinity.objects.clear_cache()
        super().tearDown()

    def test_getter_returns_row(self) -> None:
        celestial = AffinityFactory(name=AFFINITY_CELESTIAL)
        primal = AffinityFactory(name=AFFINITY_PRIMAL)
        abyssal = AffinityFactory(name=AFFINITY_ABYSSAL)
        self.assertEqual(Affinity.objects.get_celestial_affinity(), celestial)
        self.assertEqual(Affinity.objects.get_primal_affinity(), primal)
        self.assertEqual(Affinity.objects.get_abyssal_affinity(), abyssal)

    def test_getter_cached_no_query(self) -> None:
        AffinityFactory(name=AFFINITY_CELESTIAL)
        Affinity.objects.get_celestial_affinity()
        with self.assertNumQueries(0):
            Affinity.objects.get_celestial_affinity()

    def test_missing_row_raises(self) -> None:
        with self.assertRaises(AffinityNotConfigured):
            Affinity.objects.get_primal_affinity()

    def test_renamed_row_raises(self) -> None:
        AffinityFactory(name="Celestials")
        with self.assertRaises(AffinityNotConfigured):
            Affinity.objects.get_celestial_affinity()
