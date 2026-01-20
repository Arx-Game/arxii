from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.magic.models import Affinity, CharacterAura, CharacterResonance, Resonance
from world.magic.types import AffinityType, ResonanceScope, ResonanceStrength


class AffinityModelTests(TestCase):
    """Tests for the Affinity model."""

    @classmethod
    def setUpTestData(cls):
        cls.celestial = Affinity.objects.create(
            affinity_type=AffinityType.CELESTIAL,
            name="Celestial",
            description="Magic of divine ideals and impossible virtue.",
            admin_notes="High control, never backfires, demands paragon lifestyle.",
        )

    def test_affinity_str(self):
        """Test string representation."""
        self.assertEqual(str(self.celestial), "Celestial")

    def test_affinity_natural_key(self):
        """Test natural key lookup."""
        self.assertEqual(
            Affinity.objects.get_by_natural_key("celestial"),
            self.celestial,
        )

    def test_affinity_unique_type(self):
        """Test that affinity_type is unique."""
        with self.assertRaises(IntegrityError):
            Affinity.objects.create(
                affinity_type=AffinityType.CELESTIAL,
                name="Duplicate Celestial",
                description="Should fail.",
            )


class ResonanceModelTests(TestCase):
    """Tests for the Resonance model."""

    @classmethod
    def setUpTestData(cls):
        cls.primal = Affinity.objects.create(
            affinity_type=AffinityType.PRIMAL,
            name="Primal",
            description="Magic of the world.",
        )
        cls.shadows = Resonance.objects.create(
            name="Shadows",
            slug="shadows",
            default_affinity=cls.primal,
            description="Darkness, stealth, concealment.",
        )

    def test_resonance_str(self):
        """Test string representation."""
        self.assertEqual(str(self.shadows), "Shadows")

    def test_resonance_natural_key(self):
        """Test natural key lookup."""
        self.assertEqual(
            Resonance.objects.get_by_natural_key("shadows"),
            self.shadows,
        )

    def test_resonance_slug_unique(self):
        """Test that slug is unique."""
        with self.assertRaises(IntegrityError):
            Resonance.objects.create(
                name="Different Shadows",
                slug="shadows",
                default_affinity=self.primal,
                description="Should fail.",
            )


class CharacterAuraModelTests(TestCase):
    """Tests for the CharacterAura model."""

    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterFactory()
        cls.aura = CharacterAura.objects.create(
            character=cls.character,
            celestial=Decimal("10.00"),
            primal=Decimal("75.00"),
            abyssal=Decimal("15.00"),
        )

    def test_aura_str(self):
        """Test string representation."""
        self.assertIn(str(self.character), str(self.aura))

    def test_aura_total_equals_100(self):
        """Test that aura percentages sum to 100."""
        total = self.aura.celestial + self.aura.primal + self.aura.abyssal
        self.assertEqual(total, Decimal("100.00"))

    def test_aura_one_per_character(self):
        """Test that a character can only have one aura."""
        with self.assertRaises(ValidationError):
            CharacterAura.objects.create(
                character=self.character,
                celestial=Decimal("33.33"),
                primal=Decimal("33.34"),
                abyssal=Decimal("33.33"),
            )

    def test_aura_dominant_affinity(self):
        """Test dominant_affinity property."""
        self.assertEqual(self.aura.dominant_affinity, AffinityType.PRIMAL)

    def test_aura_validation_requires_100_percent(self):
        """Test that aura validation requires percentages to sum to 100."""
        character2 = CharacterFactory()
        with self.assertRaises(ValidationError):
            CharacterAura.objects.create(
                character=character2,
                celestial=Decimal("50.00"),
                primal=Decimal("50.00"),
                abyssal=Decimal("50.00"),  # Total is 150, should fail
            )


class CharacterResonanceModelTests(TestCase):
    """Tests for the CharacterResonance model."""

    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterFactory()
        cls.primal = Affinity.objects.create(
            affinity_type=AffinityType.PRIMAL,
            name="Primal",
            description="Magic of the world.",
        )
        cls.shadows = Resonance.objects.create(
            name="Shadows",
            slug="shadows",
            default_affinity=cls.primal,
            description="Darkness and concealment.",
        )
        cls.char_resonance = CharacterResonance.objects.create(
            character=cls.character,
            resonance=cls.shadows,
            scope=ResonanceScope.SELF,
            strength=ResonanceStrength.MODERATE,
            flavor_text="A shadowy presence lingers around them.",
        )

    def test_character_resonance_str(self):
        """Test string representation."""
        result = str(self.char_resonance)
        self.assertIn("Shadows", result)
        self.assertIn(str(self.character), result)

    def test_character_resonance_unique_together(self):
        """Test that a character can't have duplicate resonances."""
        with self.assertRaises(IntegrityError):
            CharacterResonance.objects.create(
                character=self.character,
                resonance=self.shadows,
                scope=ResonanceScope.SELF,
                strength=ResonanceStrength.MAJOR,
            )

    def test_character_can_have_multiple_resonances(self):
        """Test that a character can have multiple different resonances."""
        majesty = Resonance.objects.create(
            name="Majesty",
            slug="majesty",
            default_affinity=self.primal,
            description="Regal presence.",
        )
        CharacterResonance.objects.create(
            character=self.character,
            resonance=majesty,
            scope=ResonanceScope.AREA,
            strength=ResonanceStrength.MINOR,
        )
        self.assertEqual(self.character.resonances.count(), 2)
