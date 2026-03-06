"""Tests for CharacterAffinityTotal and CharacterResonanceTotal models."""

from django.db import IntegrityError
from django.db.models import ProtectedError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import AffinityFactory, ResonanceFactory
from world.magic.models import CharacterAffinityTotal, CharacterResonanceTotal


class CharacterAffinityTotalModelTests(TestCase):
    """Tests for CharacterAffinityTotal model."""

    @classmethod
    def setUpTestData(cls):
        cls.character_sheet = CharacterSheetFactory()
        cls.celestial = AffinityFactory(name="Celestial")
        cls.primal = AffinityFactory(name="Primal")
        cls.abyssal = AffinityFactory(name="Abyssal")

    def test_character_affinity_total_creation(self):
        """Test creating an affinity total for a character."""
        total = CharacterAffinityTotal.objects.create(
            character=self.character_sheet,
            affinity=self.abyssal,
            total=100,
        )
        self.assertEqual(total.total, 100)
        self.assertEqual(total.affinity, self.abyssal)

    def test_character_affinity_total_str(self):
        """Test string representation of affinity total."""
        total = CharacterAffinityTotal.objects.create(
            character=self.character_sheet,
            affinity=self.celestial,
            total=50,
        )
        result = str(total)
        self.assertIn("Celestial", result)
        self.assertIn("50", result)

    def test_character_affinity_total_unique_together(self):
        """Test that character can only have one total per affinity."""
        CharacterAffinityTotal.objects.create(
            character=self.character_sheet,
            affinity=self.primal,
            total=75,
        )
        with self.assertRaises(IntegrityError):
            CharacterAffinityTotal.objects.create(
                character=self.character_sheet,
                affinity=self.primal,
                total=100,
            )

    def test_character_can_have_multiple_affinities(self):
        """Test that a character can have totals for all three affinities."""
        CharacterAffinityTotal.objects.create(
            character=self.character_sheet,
            affinity=self.celestial,
            total=30,
        )
        CharacterAffinityTotal.objects.create(
            character=self.character_sheet,
            affinity=self.primal,
            total=50,
        )
        CharacterAffinityTotal.objects.create(
            character=self.character_sheet,
            affinity=self.abyssal,
            total=20,
        )
        self.assertEqual(self.character_sheet.affinity_totals.count(), 3)

    def test_affinity_total_default_value(self):
        """Test that total defaults to 0."""
        total = CharacterAffinityTotal.objects.create(
            character=self.character_sheet,
            affinity=self.celestial,
        )
        self.assertEqual(total.total, 0)


class CharacterResonanceTotalModelTests(TestCase):
    """Tests for CharacterResonanceTotal model."""

    @classmethod
    def setUpTestData(cls):
        cls.character_sheet = CharacterSheetFactory()
        cls.shadows = ResonanceFactory(name="Shadows")

    def test_character_resonance_total_creation(self):
        """Test creating a resonance total for a character."""
        total = CharacterResonanceTotal.objects.create(
            character=self.character_sheet,
            resonance=self.shadows,
            total=50,
        )
        self.assertEqual(total.total, 50)
        self.assertEqual(total.resonance, self.shadows)

    def test_character_resonance_total_str(self):
        """Test string representation of resonance total."""
        total = CharacterResonanceTotal.objects.create(
            character=self.character_sheet,
            resonance=self.shadows,
            total=75,
        )
        result = str(total)
        self.assertIn("Shadows", result)
        self.assertIn("75", result)

    def test_character_resonance_total_unique_together(self):
        """Test that character can only have one total per resonance."""
        CharacterResonanceTotal.objects.create(
            character=self.character_sheet,
            resonance=self.shadows,
            total=50,
        )
        with self.assertRaises(IntegrityError):
            CharacterResonanceTotal.objects.create(
                character=self.character_sheet,
                resonance=self.shadows,
                total=100,
            )

    def test_character_can_have_multiple_resonance_totals(self):
        """Test that a character can have totals for multiple resonances."""
        majesty = ResonanceFactory(name="Majesty")
        CharacterResonanceTotal.objects.create(
            character=self.character_sheet,
            resonance=self.shadows,
            total=30,
        )
        CharacterResonanceTotal.objects.create(
            character=self.character_sheet,
            resonance=majesty,
            total=20,
        )
        self.assertEqual(self.character_sheet.resonance_totals.count(), 2)

    def test_resonance_total_default_value(self):
        """Test that total defaults to 0."""
        total = CharacterResonanceTotal.objects.create(
            character=self.character_sheet,
            resonance=self.shadows,
        )
        self.assertEqual(total.total, 0)

    def test_resonance_total_protect_on_delete(self):
        """Test that deleting Resonance is protected when totals exist."""
        test_resonance = ResonanceFactory(name="TestResonance")
        CharacterResonanceTotal.objects.create(
            character=self.character_sheet,
            resonance=test_resonance,
            total=50,
        )
        with self.assertRaises(ProtectedError):
            test_resonance.delete()
