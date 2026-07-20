"""Tests for the ceremonies seed cluster (#2393)."""

from django.test import TestCase

from world.ceremonies.constants import CeremonyTypeKey
from world.ceremonies.models import CeremonyType
from world.ceremonies.seeds import seed_ceremony_types


class SeedCeremonyTypesTests(TestCase):
    def test_seeds_all_four_types(self) -> None:
        seed_ceremony_types()
        keys = set(CeremonyType.objects.values_list("key", flat=True))
        self.assertEqual(
            keys,
            {
                CeremonyTypeKey.FUNERAL,
                CeremonyTypeKey.BLESSING,
                CeremonyTypeKey.SERMON,
                CeremonyTypeKey.SEANCE,
            },
        )

    def test_idempotent(self) -> None:
        seed_ceremony_types()
        seed_ceremony_types()
        self.assertEqual(CeremonyType.objects.count(), 4)
