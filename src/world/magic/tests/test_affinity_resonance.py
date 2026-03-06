"""Tests for Affinity and Resonance models."""

from django.db import IntegrityError
from django.test import TestCase

from world.magic.factories import AffinityFactory, ResonanceFactory
from world.magic.models import Affinity, Resonance
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory


class AffinityModelTests(TestCase):
    """Tests for the Affinity model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.celestial = AffinityFactory(name="Celestial")

    def test_str(self) -> None:
        self.assertEqual(str(self.celestial), "Celestial")

    def test_unique_name(self) -> None:
        with self.assertRaises(IntegrityError):
            Affinity.objects.create(name="Celestial")

    def test_modifier_target_link(self) -> None:
        """Affinity can be linked from a ModifierTarget."""
        cat = ModifierCategoryFactory(name="affinity")
        mt = ModifierTargetFactory(name="Celestial", category=cat, target_affinity=self.celestial)
        self.assertEqual(mt.target_affinity, self.celestial)
        self.assertEqual(self.celestial.modifier_target, mt)

    def test_no_modifier_target(self) -> None:
        """Affinity can exist without a ModifierTarget pointing to it."""
        aff = AffinityFactory(name="Primal")
        self.assertFalse(hasattr(aff, "modifier_target") and aff.modifier_target is not None)


class ResonanceModelTests(TestCase):
    """Tests for the Resonance model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.celestial = AffinityFactory(name="CelestialRes")
        cls.abyssal = AffinityFactory(name="AbyssalRes")
        cls.bene = ResonanceFactory(name="Bene", affinity=cls.celestial)
        cls.praedari = ResonanceFactory(name="Praedari", affinity=cls.abyssal)

    def test_str(self) -> None:
        self.assertEqual(str(self.bene), "Bene (CelestialRes)")

    def test_unique_name(self) -> None:
        with self.assertRaises(IntegrityError):
            Resonance.objects.create(name="Bene", affinity=self.celestial)

    def test_affinity_fk(self) -> None:
        self.assertEqual(self.bene.affinity, self.celestial)

    def test_opposite_pair(self) -> None:
        """Resonances can reference their opposite."""
        self.bene.opposite = self.praedari
        self.bene.save()
        self.praedari.refresh_from_db()
        self.assertEqual(self.bene.opposite, self.praedari)
        self.assertEqual(self.praedari.opposite_of, self.bene)

    def test_modifier_target_link(self) -> None:
        """Resonance can be linked from a ModifierTarget."""
        cat = ModifierCategoryFactory(name="resonance")
        mt = ModifierTargetFactory(name="Bene", category=cat, target_resonance=self.bene)
        self.assertEqual(mt.target_resonance, self.bene)
        self.assertEqual(self.bene.modifier_target, mt)

    def test_affinity_reverse_relation(self) -> None:
        """Affinity.resonances returns related resonances."""
        resonance_names = list(self.celestial.resonances.values_list("name", flat=True))
        self.assertIn("Bene", resonance_names)
