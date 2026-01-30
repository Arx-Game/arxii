"""Tests for CharacterAffinityTotal and CharacterResonanceTotal models."""

from django.db import IntegrityError
from django.db.models import ProtectedError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.models import CharacterAffinityTotal, CharacterResonanceTotal
from world.magic.types import AffinityType
from world.mechanics.models import ModifierCategory, ModifierType


class CharacterAffinityTotalModelTests(TestCase):
    """Tests for CharacterAffinityTotal model."""

    @classmethod
    def setUpTestData(cls):
        cls.character_sheet = CharacterSheetFactory()

    def test_character_affinity_total_creation(self):
        """Test creating an affinity total for a character."""
        total = CharacterAffinityTotal.objects.create(
            character=self.character_sheet,
            affinity_type=AffinityType.ABYSSAL,
            total=100,
        )
        self.assertEqual(total.total, 100)
        self.assertEqual(total.affinity_type, AffinityType.ABYSSAL)

    def test_character_affinity_total_str(self):
        """Test string representation of affinity total."""
        total = CharacterAffinityTotal.objects.create(
            character=self.character_sheet,
            affinity_type=AffinityType.CELESTIAL,
            total=50,
        )
        result = str(total)
        self.assertIn("celestial", result)
        self.assertIn("50", result)

    def test_character_affinity_total_unique_together(self):
        """Test that character can only have one total per affinity type."""
        CharacterAffinityTotal.objects.create(
            character=self.character_sheet,
            affinity_type=AffinityType.PRIMAL,
            total=75,
        )
        with self.assertRaises(IntegrityError):
            CharacterAffinityTotal.objects.create(
                character=self.character_sheet,
                affinity_type=AffinityType.PRIMAL,
                total=100,
            )

    def test_character_can_have_multiple_affinity_types(self):
        """Test that a character can have totals for all three affinity types."""
        CharacterAffinityTotal.objects.create(
            character=self.character_sheet,
            affinity_type=AffinityType.CELESTIAL,
            total=30,
        )
        CharacterAffinityTotal.objects.create(
            character=self.character_sheet,
            affinity_type=AffinityType.PRIMAL,
            total=50,
        )
        CharacterAffinityTotal.objects.create(
            character=self.character_sheet,
            affinity_type=AffinityType.ABYSSAL,
            total=20,
        )
        self.assertEqual(self.character_sheet.affinity_totals.count(), 3)

    def test_affinity_total_default_value(self):
        """Test that total defaults to 0."""
        total = CharacterAffinityTotal.objects.create(
            character=self.character_sheet,
            affinity_type=AffinityType.CELESTIAL,
        )
        self.assertEqual(total.total, 0)


class CharacterResonanceTotalModelTests(TestCase):
    """Tests for CharacterResonanceTotal model."""

    @classmethod
    def setUpTestData(cls):
        cls.character_sheet = CharacterSheetFactory()
        cls.resonance_category, _ = ModifierCategory.objects.get_or_create(
            name="resonance",
            defaults={"description": "Magical resonances"},
        )
        cls.shadows, _ = ModifierType.objects.get_or_create(
            name="Shadows",
            category=cls.resonance_category,
            defaults={"description": "Darkness and concealment."},
        )

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
        majesty, _ = ModifierType.objects.get_or_create(
            name="Majesty",
            category=self.resonance_category,
            defaults={"description": "Regal presence."},
        )
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
        """Test that deleting ModifierType is protected when totals exist."""
        # Create a new resonance specifically for this test
        test_resonance = ModifierType.objects.create(
            name="TestResonance",
            category=self.resonance_category,
            description="Test resonance for deletion test.",
        )
        CharacterResonanceTotal.objects.create(
            character=self.character_sheet,
            resonance=test_resonance,
            total=50,
        )
        with self.assertRaises(ProtectedError):
            test_resonance.delete()
