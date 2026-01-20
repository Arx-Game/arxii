from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.magic.models import (
    Affinity,
    AnimaRitualType,
    CharacterAnima,
    CharacterAnimaRitual,
    CharacterAura,
    CharacterGift,
    CharacterPower,
    CharacterResonance,
    Gift,
    IntensityTier,
    Power,
    Resonance,
)
from world.magic.types import (
    AffinityType,
    AnimaRitualCategory,
    ResonanceScope,
    ResonanceStrength,
)


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


# =============================================================================
# Phase 2: Gifts & Powers Tests
# =============================================================================


class IntensityTierModelTests(TestCase):
    """Tests for the IntensityTier model."""

    @classmethod
    def setUpTestData(cls):
        cls.base_tier = IntensityTier.objects.create(
            name="Base",
            threshold=10,
            control_modifier=0,
            description="Standard power effect.",
        )
        cls.enhanced_tier = IntensityTier.objects.create(
            name="Enhanced",
            threshold=50,
            control_modifier=10,
            description="Stronger effect with additional targets.",
        )

    def test_intensity_tier_str(self):
        """Test string representation."""
        self.assertEqual(str(self.base_tier), "Base (10+)")

    def test_intensity_tier_ordering(self):
        """Test that tiers are ordered by threshold."""
        tiers = list(IntensityTier.objects.all())
        self.assertEqual(tiers[0], self.base_tier)
        self.assertEqual(tiers[1], self.enhanced_tier)

    def test_intensity_tier_unique_threshold(self):
        """Test that threshold is unique."""
        with self.assertRaises(IntegrityError):
            IntensityTier.objects.create(
                name="Duplicate",
                threshold=10,
            )


class GiftModelTests(TestCase):
    """Tests for the Gift model."""

    @classmethod
    def setUpTestData(cls):
        cls.abyssal = Affinity.objects.create(
            affinity_type=AffinityType.ABYSSAL,
            name="Abyssal",
            description="Dark magic.",
        )
        cls.primal = Affinity.objects.create(
            affinity_type=AffinityType.PRIMAL,
            name="Primal",
            description="Magic of the world.",
        )
        cls.shadows = Resonance.objects.create(
            name="Shadows",
            slug="shadows",
            default_affinity=cls.primal,
        )
        cls.gift = Gift.objects.create(
            name="Shadow Majesty",
            slug="shadow-majesty",
            affinity=cls.abyssal,
            description="Dark regal influence.",
            level_requirement=1,
        )
        cls.gift.resonances.add(cls.shadows)

    def test_gift_str(self):
        """Test string representation."""
        self.assertEqual(str(self.gift), "Shadow Majesty")

    def test_gift_natural_key(self):
        """Test natural key lookup."""
        self.assertEqual(
            Gift.objects.get_by_natural_key("shadow-majesty"),
            self.gift,
        )

    def test_gift_has_resonances(self):
        """Test that gift can have resonances."""
        self.assertEqual(self.gift.resonances.count(), 1)
        self.assertIn(self.shadows, self.gift.resonances.all())


class PowerModelTests(TestCase):
    """Tests for the Power model."""

    @classmethod
    def setUpTestData(cls):
        cls.abyssal = Affinity.objects.create(
            affinity_type=AffinityType.ABYSSAL,
            name="Abyssal",
            description="Dark magic.",
        )
        cls.gift = Gift.objects.create(
            name="Shadow Majesty",
            slug="shadow-majesty",
            affinity=cls.abyssal,
            description="Dark regal influence.",
        )
        cls.power = Power.objects.create(
            name="Castigate",
            slug="castigate",
            gift=cls.gift,
            affinity=cls.abyssal,
            base_intensity=10,
            base_control=10,
            anima_cost=2,
            level_requirement=1,
            description="A shadowy bolt of force.",
        )

    def test_power_str(self):
        """Test string representation."""
        self.assertEqual(str(self.power), "Castigate (Shadow Majesty)")

    def test_power_natural_key(self):
        """Test natural key lookup."""
        self.assertEqual(
            Power.objects.get_by_natural_key("castigate"),
            self.power,
        )

    def test_power_belongs_to_gift(self):
        """Test that power belongs to a gift."""
        self.assertEqual(self.power.gift, self.gift)
        self.assertIn(self.power, self.gift.powers.all())


class CharacterGiftModelTests(TestCase):
    """Tests for the CharacterGift model."""

    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterFactory()
        cls.abyssal = Affinity.objects.create(
            affinity_type=AffinityType.ABYSSAL,
            name="Abyssal",
            description="Dark magic.",
        )
        cls.gift = Gift.objects.create(
            name="Shadow Majesty",
            slug="shadow-majesty",
            affinity=cls.abyssal,
        )
        cls.char_gift = CharacterGift.objects.create(
            character=cls.character,
            gift=cls.gift,
        )

    def test_character_gift_str(self):
        """Test string representation."""
        result = str(self.char_gift)
        self.assertIn("Shadow Majesty", result)

    def test_character_gift_unique_together(self):
        """Test that character can't have duplicate gifts."""
        with self.assertRaises(IntegrityError):
            CharacterGift.objects.create(
                character=self.character,
                gift=self.gift,
            )


class CharacterPowerModelTests(TestCase):
    """Tests for the CharacterPower model."""

    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterFactory()
        cls.abyssal = Affinity.objects.create(
            affinity_type=AffinityType.ABYSSAL,
            name="Abyssal",
            description="Dark magic.",
        )
        cls.gift = Gift.objects.create(
            name="Shadow Majesty",
            slug="shadow-majesty",
            affinity=cls.abyssal,
        )
        cls.power = Power.objects.create(
            name="Castigate",
            slug="castigate",
            gift=cls.gift,
            affinity=cls.abyssal,
        )
        cls.char_power = CharacterPower.objects.create(
            character=cls.character,
            power=cls.power,
        )

    def test_character_power_str(self):
        """Test string representation."""
        result = str(self.char_power)
        self.assertIn("Castigate", result)

    def test_character_power_unique_together(self):
        """Test that character can't have duplicate powers."""
        with self.assertRaises(IntegrityError):
            CharacterPower.objects.create(
                character=self.character,
                power=self.power,
            )

    def test_character_power_tracks_usage(self):
        """Test that power tracks times_used."""
        self.assertEqual(self.char_power.times_used, 0)
        self.char_power.times_used += 1
        self.char_power.save()
        self.char_power.refresh_from_db()
        self.assertEqual(self.char_power.times_used, 1)


# =============================================================================
# Phase 3: Anima System Tests
# =============================================================================


class CharacterAnimaModelTests(TestCase):
    """Tests for the CharacterAnima model."""

    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterFactory()
        cls.anima = CharacterAnima.objects.create(
            character=cls.character,
            current=8,
            maximum=10,
        )

    def test_anima_str(self):
        """Test string representation."""
        result = str(self.anima)
        self.assertIn(str(self.character), result)
        self.assertIn("8/10", result)

    def test_anima_one_per_character(self):
        """Test that a character can only have one anima record."""
        with self.assertRaises(ValidationError):
            CharacterAnima.objects.create(
                character=self.character,
                current=5,
                maximum=10,
            )

    def test_anima_current_cannot_exceed_maximum(self):
        """Test that current anima cannot exceed maximum."""
        character2 = CharacterFactory()
        with self.assertRaises(ValidationError):
            CharacterAnima.objects.create(
                character=character2,
                current=15,
                maximum=10,
            )

    def test_anima_update_current(self):
        """Test that current anima can be updated."""
        self.anima.current = 5
        self.anima.save()
        self.anima.refresh_from_db()
        self.assertEqual(self.anima.current, 5)


class AnimaRitualTypeModelTests(TestCase):
    """Tests for the AnimaRitualType model."""

    @classmethod
    def setUpTestData(cls):
        cls.meditation = AnimaRitualType.objects.create(
            name="Meditation",
            slug="meditation",
            category=AnimaRitualCategory.SOLITARY,
            description="Quiet reflection and centering.",
            base_recovery=5,
        )

    def test_ritual_type_str(self):
        """Test string representation."""
        self.assertEqual(str(self.meditation), "Meditation")

    def test_ritual_type_natural_key(self):
        """Test natural key lookup."""
        self.assertEqual(
            AnimaRitualType.objects.get_by_natural_key("meditation"),
            self.meditation,
        )

    def test_ritual_type_slug_unique(self):
        """Test that slug is unique."""
        with self.assertRaises(IntegrityError):
            AnimaRitualType.objects.create(
                name="Different Meditation",
                slug="meditation",
                category=AnimaRitualCategory.SOLITARY,
            )

    def test_ritual_type_ordering(self):
        """Test that types are ordered by category then name."""
        collaborative = AnimaRitualType.objects.create(
            name="Group Ritual",
            slug="group-ritual",
            category=AnimaRitualCategory.COLLABORATIVE,
        )
        types = list(AnimaRitualType.objects.all())
        # Collaborative comes before Solitary alphabetically
        self.assertEqual(types[0], collaborative)
        self.assertEqual(types[1], self.meditation)


class CharacterAnimaRitualModelTests(TestCase):
    """Tests for the CharacterAnimaRitual model."""

    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterFactory()
        cls.ritual_type = AnimaRitualType.objects.create(
            name="Meditation",
            slug="meditation",
            category=AnimaRitualCategory.SOLITARY,
        )
        cls.ritual = CharacterAnimaRitual.objects.create(
            character=cls.character,
            ritual_type=cls.ritual_type,
            personal_description="I sit beneath the old oak tree at dawn.",
            is_primary=True,
        )

    def test_ritual_str(self):
        """Test string representation."""
        result = str(self.ritual)
        self.assertIn("Meditation", result)
        self.assertIn(str(self.character), result)

    def test_ritual_unique_together(self):
        """Test that character can't have duplicate ritual types."""
        with self.assertRaises(IntegrityError):
            CharacterAnimaRitual.objects.create(
                character=self.character,
                ritual_type=self.ritual_type,
                personal_description="Another description.",
            )

    def test_character_can_have_multiple_rituals(self):
        """Test that character can have multiple different rituals."""
        collaborative_type = AnimaRitualType.objects.create(
            name="Group Prayer",
            slug="group-prayer",
            category=AnimaRitualCategory.COLLABORATIVE,
        )
        CharacterAnimaRitual.objects.create(
            character=self.character,
            ritual_type=collaborative_type,
            personal_description="We gather in the temple at sunset.",
        )
        self.assertEqual(self.character.anima_rituals.count(), 2)

    def test_ritual_tracks_performance(self):
        """Test that ritual tracks times_performed."""
        self.assertEqual(self.ritual.times_performed, 0)
        self.ritual.times_performed += 1
        self.ritual.save()
        self.ritual.refresh_from_db()
        self.assertEqual(self.ritual.times_performed, 1)
