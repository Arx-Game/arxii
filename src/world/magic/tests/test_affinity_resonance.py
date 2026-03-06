"""Tests for Affinity and Resonance models."""

from django.db import IntegrityError
from django.test import TestCase

from world.magic.factories import AffinityFactory, ResonanceFactory


class AffinityModelTests(TestCase):
    """Tests for the Affinity model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.celestial = AffinityFactory(name="Celestial")

    def test_str(self) -> None:
        self.assertEqual(str(self.celestial), "Celestial")

    def test_unique_name(self) -> None:
        with self.assertRaises(IntegrityError):
            AffinityFactory(name="Celestial")

    def test_modifier_target_nullable(self) -> None:
        """Affinity can exist without a modifier_target link."""
        aff = AffinityFactory(name="Primal", modifier_target=None)
        self.assertIsNone(aff.modifier_target)


class ResonanceModelTests(TestCase):
    """Tests for the Resonance model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.celestial = AffinityFactory(name="Celestial")
        cls.abyssal = AffinityFactory(name="Abyssal")
        cls.bene = ResonanceFactory(name="Bene", affinity=cls.celestial)
        cls.praedari = ResonanceFactory(name="Praedari", affinity=cls.abyssal)

    def test_str(self) -> None:
        self.assertEqual(str(self.bene), "Bene (Celestial)")

    def test_unique_name(self) -> None:
        with self.assertRaises(IntegrityError):
            ResonanceFactory(name="Bene", affinity=self.celestial)

    def test_affinity_fk(self) -> None:
        self.assertEqual(self.bene.affinity, self.celestial)

    def test_opposite_pair(self) -> None:
        """Resonances can reference their opposite."""
        self.bene.opposite = self.praedari
        self.bene.save()
        self.praedari.refresh_from_db()
        self.assertEqual(self.bene.opposite, self.praedari)
        self.assertEqual(self.praedari.opposite_of, self.bene)

    def test_modifier_target_nullable(self) -> None:
        res = ResonanceFactory(name="Sylva", affinity=self.celestial, modifier_target=None)
        self.assertIsNone(res.modifier_target)

    def test_affinity_reverse_relation(self) -> None:
        """Affinity.resonances returns related resonances."""
        resonance_names = list(self.celestial.resonances.values_list("name", flat=True))
        self.assertIn("Bene", resonance_names)
