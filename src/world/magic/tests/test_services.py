"""Tests for magic system service functions."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.models import CharacterAffinityTotal, CharacterResonanceTotal
from world.magic.services import get_aura_percentages
from world.magic.types import AffinityType
from world.mechanics.models import ModifierCategory, ModifierType


class GetAuraPercentagesTests(TestCase):
    """Tests for the get_aura_percentages service function."""

    @classmethod
    def setUpTestData(cls):
        cls.character_sheet = CharacterSheetFactory()

        # Create affinity category and types
        cls.affinity_category, _ = ModifierCategory.objects.get_or_create(
            name="affinity",
            defaults={"description": "Magical affinities"},
        )
        cls.celestial_affinity, _ = ModifierType.objects.get_or_create(
            name="Celestial",
            category=cls.affinity_category,
            defaults={"description": "The Celestial affinity."},
        )
        cls.primal_affinity, _ = ModifierType.objects.get_or_create(
            name="Primal",
            category=cls.affinity_category,
            defaults={"description": "The Primal affinity."},
        )
        cls.abyssal_affinity, _ = ModifierType.objects.get_or_create(
            name="Abyssal",
            category=cls.affinity_category,
            defaults={"description": "The Abyssal affinity."},
        )

        # Create resonance category
        cls.resonance_category, _ = ModifierCategory.objects.get_or_create(
            name="resonance",
            defaults={"description": "Magical resonances"},
        )

    def test_empty_totals_returns_even_split(self):
        """Empty totals return even split."""
        result = get_aura_percentages(self.character_sheet)
        self.assertAlmostEqual(result.celestial, 33.33, places=1)
        self.assertAlmostEqual(result.primal, 33.33, places=1)
        self.assertAlmostEqual(result.abyssal, 33.34, places=1)

    def test_single_affinity_total(self):
        """Single affinity gives 100%."""
        CharacterAffinityTotal.objects.create(
            character=self.character_sheet,
            affinity_type=AffinityType.ABYSSAL,
            total=100,
        )
        result = get_aura_percentages(self.character_sheet)
        self.assertEqual(result.abyssal, 100.0)
        self.assertEqual(result.celestial, 0.0)
        self.assertEqual(result.primal, 0.0)

    def test_mixed_affinity_totals(self):
        """Mixed totals calculate correct percentages."""
        CharacterAffinityTotal.objects.create(
            character=self.character_sheet,
            affinity_type=AffinityType.CELESTIAL,
            total=50,
        )
        CharacterAffinityTotal.objects.create(
            character=self.character_sheet,
            affinity_type=AffinityType.ABYSSAL,
            total=50,
        )
        result = get_aura_percentages(self.character_sheet)
        self.assertEqual(result.celestial, 50.0)
        self.assertEqual(result.abyssal, 50.0)
        self.assertEqual(result.primal, 0.0)

    def test_all_three_affinities(self):
        """All three affinities calculate correctly."""
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
        result = get_aura_percentages(self.character_sheet)
        self.assertEqual(result.celestial, 30.0)
        self.assertEqual(result.primal, 50.0)
        self.assertEqual(result.abyssal, 20.0)

    def test_resonance_contributes_to_affiliated_affinity(self):
        """Resonance totals contribute to their affiliated affinity."""
        # Create a resonance with an affiliated affinity
        shadows = ModifierType.objects.create(
            name="Shadows",
            category=self.resonance_category,
            description="Darkness and concealment.",
            affiliated_affinity=self.abyssal_affinity,
        )

        # Add resonance total
        CharacterResonanceTotal.objects.create(
            character=self.character_sheet,
            resonance=shadows,
            total=100,
        )

        result = get_aura_percentages(self.character_sheet)
        self.assertEqual(result.abyssal, 100.0)
        self.assertEqual(result.celestial, 0.0)
        self.assertEqual(result.primal, 0.0)

    def test_resonance_without_affiliated_affinity_does_not_contribute(self):
        """Resonances without affiliated_affinity don't affect aura."""
        # Create a resonance without an affiliated affinity
        unaffiliated = ModifierType.objects.create(
            name="Unaffiliated",
            category=self.resonance_category,
            description="A resonance without affiliation.",
            affiliated_affinity=None,
        )

        CharacterResonanceTotal.objects.create(
            character=self.character_sheet,
            resonance=unaffiliated,
            total=100,
        )

        result = get_aura_percentages(self.character_sheet)
        # Should return even split since no effective affinity totals
        self.assertAlmostEqual(result.celestial, 33.33, places=1)
        self.assertAlmostEqual(result.primal, 33.33, places=1)
        self.assertAlmostEqual(result.abyssal, 33.34, places=1)

    def test_affinity_and_resonance_combined(self):
        """Affinity totals and resonance contributions combine correctly."""
        # Direct affinity total
        CharacterAffinityTotal.objects.create(
            character=self.character_sheet,
            affinity_type=AffinityType.CELESTIAL,
            total=50,
        )

        # Resonance contributing to abyssal
        shadows = ModifierType.objects.create(
            name="DarkShadows",
            category=self.resonance_category,
            description="Darkness and concealment.",
            affiliated_affinity=self.abyssal_affinity,
        )
        CharacterResonanceTotal.objects.create(
            character=self.character_sheet,
            resonance=shadows,
            total=50,
        )

        result = get_aura_percentages(self.character_sheet)
        self.assertEqual(result.celestial, 50.0)
        self.assertEqual(result.abyssal, 50.0)
        self.assertEqual(result.primal, 0.0)

    def test_multiple_resonances_same_affinity(self):
        """Multiple resonances with same affiliated affinity stack."""
        # Two resonances both affiliated with celestial
        light = ModifierType.objects.create(
            name="Light",
            category=self.resonance_category,
            description="Radiance and illumination.",
            affiliated_affinity=self.celestial_affinity,
        )
        hope = ModifierType.objects.create(
            name="Hope",
            category=self.resonance_category,
            description="Optimism and aspiration.",
            affiliated_affinity=self.celestial_affinity,
        )

        CharacterResonanceTotal.objects.create(
            character=self.character_sheet,
            resonance=light,
            total=30,
        )
        CharacterResonanceTotal.objects.create(
            character=self.character_sheet,
            resonance=hope,
            total=70,
        )

        result = get_aura_percentages(self.character_sheet)
        self.assertEqual(result.celestial, 100.0)
        self.assertEqual(result.primal, 0.0)
        self.assertEqual(result.abyssal, 0.0)


class GetAuraPercentagesEdgeCasesTests(TestCase):
    """Edge case tests for get_aura_percentages."""

    @classmethod
    def setUpTestData(cls):
        cls.character_sheet = CharacterSheetFactory()

        # Create affinity category and types
        cls.affinity_category, _ = ModifierCategory.objects.get_or_create(
            name="affinity",
            defaults={"description": "Magical affinities"},
        )
        cls.primal_affinity, _ = ModifierType.objects.get_or_create(
            name="Primal",
            category=cls.affinity_category,
            defaults={"description": "The Primal affinity."},
        )

        cls.resonance_category, _ = ModifierCategory.objects.get_or_create(
            name="resonance",
            defaults={"description": "Magical resonances"},
        )

    def test_zero_total_value(self):
        """Zero-value totals are counted but don't change percentages."""
        CharacterAffinityTotal.objects.create(
            character=self.character_sheet,
            affinity_type=AffinityType.PRIMAL,
            total=100,
        )
        CharacterAffinityTotal.objects.create(
            character=self.character_sheet,
            affinity_type=AffinityType.CELESTIAL,
            total=0,
        )

        result = get_aura_percentages(self.character_sheet)
        self.assertEqual(result.primal, 100.0)
        self.assertEqual(result.celestial, 0.0)
        self.assertEqual(result.abyssal, 0.0)

    def test_large_totals(self):
        """Large totals calculate correct percentages."""
        CharacterAffinityTotal.objects.create(
            character=self.character_sheet,
            affinity_type=AffinityType.CELESTIAL,
            total=10000,
        )
        CharacterAffinityTotal.objects.create(
            character=self.character_sheet,
            affinity_type=AffinityType.PRIMAL,
            total=30000,
        )
        CharacterAffinityTotal.objects.create(
            character=self.character_sheet,
            affinity_type=AffinityType.ABYSSAL,
            total=60000,
        )

        result = get_aura_percentages(self.character_sheet)
        self.assertEqual(result.celestial, 10.0)
        self.assertEqual(result.primal, 30.0)
        self.assertEqual(result.abyssal, 60.0)

    def test_unequal_split_with_remainder(self):
        """Unequal splits calculate correctly with potential floating point."""
        CharacterAffinityTotal.objects.create(
            character=self.character_sheet,
            affinity_type=AffinityType.CELESTIAL,
            total=1,
        )
        CharacterAffinityTotal.objects.create(
            character=self.character_sheet,
            affinity_type=AffinityType.PRIMAL,
            total=1,
        )
        CharacterAffinityTotal.objects.create(
            character=self.character_sheet,
            affinity_type=AffinityType.ABYSSAL,
            total=1,
        )

        result = get_aura_percentages(self.character_sheet)
        # Each should be roughly 33.33%
        self.assertAlmostEqual(result.celestial, 33.33, places=1)
        self.assertAlmostEqual(result.primal, 33.33, places=1)
        self.assertAlmostEqual(result.abyssal, 33.33, places=1)
        # Sum should be 100
        total = result.celestial + result.primal + result.abyssal
        self.assertAlmostEqual(total, 100.0, places=5)
