"""Tests for CharacterAffinityTotal model.

CharacterResonanceTotal was removed in Phase 2 of the resonance pivot; aura
recompute now reads `CharacterModifier` rows whose target category is
`resonance` directly. See test_services.py for the rewritten coverage.
"""

from django.db import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import AffinityFactory
from world.magic.models import CharacterAffinityTotal


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
