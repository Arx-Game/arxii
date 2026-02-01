"""Tests for magic system serializers."""

from django.test import TestCase

from world.magic.factories import (
    DraftAnimaRitualFactory,
    EffectTypeFactory,
    GiftFactory,
    MotifFactory,
    MotifResonanceAssociationFactory,
    MotifResonanceFactory,
    ResonanceAssociationFactory,
    RestrictionFactory,
    TechniqueFactory,
    TechniqueStyleFactory,
)
from world.magic.serializers import (
    DraftAnimaRitualSerializer,
    EffectTypeSerializer,
    GiftCreateSerializer,
    GiftSerializer,
    MotifResonanceAssociationSerializer,
    MotifResonanceSerializer,
    MotifSerializer,
    ResonanceAssociationSerializer,
    RestrictionSerializer,
    TechniqueSerializer,
    TechniqueStyleSerializer,
)


class TechniqueStyleSerializerTest(TestCase):
    """Tests for TechniqueStyleSerializer."""

    def test_serialization(self):
        """Test that TechniqueStyleSerializer serializes all fields."""
        style = TechniqueStyleFactory()

        serializer = TechniqueStyleSerializer(style)
        data = serializer.data

        self.assertEqual(data["name"], style.name)
        self.assertEqual(data["description"], style.description)
        self.assertIn("id", data)


class EffectTypeSerializerTest(TestCase):
    """Tests for EffectTypeSerializer."""

    def test_serialization_with_power_scaling(self):
        """Test EffectTypeSerializer with power scaling effect."""
        effect_type = EffectTypeFactory(
            name="Attack",
            base_power=10,
            base_anima_cost=2,
            has_power_scaling=True,
        )

        serializer = EffectTypeSerializer(effect_type)
        data = serializer.data

        self.assertEqual(data["name"], "Attack")
        self.assertEqual(data["base_power"], 10)
        self.assertEqual(data["base_anima_cost"], 2)
        self.assertTrue(data["has_power_scaling"])

    def test_serialization_without_power_scaling(self):
        """Test EffectTypeSerializer with binary effect (no power scaling)."""
        effect_type = EffectTypeFactory(
            name="Flight",
            base_power=None,
            has_power_scaling=False,
        )

        serializer = EffectTypeSerializer(effect_type)
        data = serializer.data

        self.assertEqual(data["name"], "Flight")
        self.assertIsNone(data["base_power"])
        self.assertFalse(data["has_power_scaling"])


class RestrictionSerializerTest(TestCase):
    """Tests for RestrictionSerializer."""

    def test_serialization(self):
        """Test RestrictionSerializer with allowed effect types."""
        effect_type = EffectTypeFactory()
        restriction = RestrictionFactory(allowed_effect_types=[effect_type])

        serializer = RestrictionSerializer(restriction)
        data = serializer.data

        self.assertEqual(data["name"], restriction.name)
        self.assertEqual(data["power_bonus"], restriction.power_bonus)
        self.assertEqual(data["allowed_effect_type_ids"], [effect_type.id])


class ResonanceAssociationSerializerTest(TestCase):
    """Tests for ResonanceAssociationSerializer."""

    def test_serialization(self):
        """Test ResonanceAssociationSerializer serializes all fields."""
        association = ResonanceAssociationFactory(category="Animals")

        serializer = ResonanceAssociationSerializer(association)
        data = serializer.data

        self.assertEqual(data["name"], association.name)
        self.assertEqual(data["description"], association.description)
        self.assertEqual(data["category"], "Animals")


class TechniqueSerializerTest(TestCase):
    """Tests for TechniqueSerializer."""

    def test_calculated_power_included(self):
        """Test that calculated_power is included in serialized data."""
        technique = TechniqueFactory()

        serializer = TechniqueSerializer(technique)
        data = serializer.data

        self.assertIn("calculated_power", data)
        self.assertIn("tier", data)

    def test_tier_derived_from_level(self):
        """Test that tier is correctly derived from level."""
        technique = TechniqueFactory(level=7)

        serializer = TechniqueSerializer(technique)
        data = serializer.data

        self.assertEqual(data["tier"], 2)  # Level 7 = Tier 2

    def test_restriction_ids_included(self):
        """Test that restriction_ids are included."""
        restriction = RestrictionFactory()
        technique = TechniqueFactory(restrictions=[restriction])

        serializer = TechniqueSerializer(technique)
        data = serializer.data

        self.assertEqual(data["restriction_ids"], [restriction.id])


class GiftSerializerTest(TestCase):
    """Tests for GiftSerializer."""

    def test_serialization(self):
        """Test GiftSerializer includes techniques and resonances."""
        gift = GiftFactory()
        TechniqueFactory(gift=gift)
        TechniqueFactory(gift=gift)

        serializer = GiftSerializer(gift)
        data = serializer.data

        self.assertEqual(data["name"], gift.name)
        self.assertEqual(len(data["techniques"]), 2)
        self.assertIn("resonance_ids", data)
        self.assertIn("affinity_name", data)


class GiftCreateSerializerTest(TestCase):
    """Tests for GiftCreateSerializer."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        from world.magic.factories import (
            AffinityModifierTypeFactory,
            ResonanceModifierTypeFactory,
        )

        cls.affinity = AffinityModifierTypeFactory()
        cls.resonance1 = ResonanceModifierTypeFactory()
        cls.resonance2 = ResonanceModifierTypeFactory()

    def test_valid_data_with_one_resonance(self):
        """Test creating gift with one resonance."""
        data = {
            "name": "Test Gift",
            "affinity": self.affinity.id,
            "resonance_ids": [self.resonance1.id],
            "description": "A test gift",
        }

        serializer = GiftCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_valid_data_with_two_resonances(self):
        """Test creating gift with two resonances."""
        data = {
            "name": "Test Gift",
            "affinity": self.affinity.id,
            "resonance_ids": [self.resonance1.id, self.resonance2.id],
            "description": "A test gift",
        }

        serializer = GiftCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_invalid_no_resonances(self):
        """Test that validation fails with zero resonances."""
        data = {
            "name": "Test Gift",
            "affinity": self.affinity.id,
            "resonance_ids": [],
            "description": "A test gift",
        }

        serializer = GiftCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("resonance_ids", serializer.errors)

    def test_invalid_too_many_resonances(self):
        """Test that validation fails with more than 2 resonances."""
        from world.magic.factories import ResonanceModifierTypeFactory

        resonance3 = ResonanceModifierTypeFactory()
        data = {
            "name": "Test Gift",
            "affinity": self.affinity.id,
            "resonance_ids": [self.resonance1.id, self.resonance2.id, resonance3.id],
            "description": "A test gift",
        }

        serializer = GiftCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("resonance_ids", serializer.errors)


class MotifSerializerTest(TestCase):
    """Tests for MotifSerializer."""

    def test_serialization_with_resonances(self):
        """Test MotifSerializer includes nested resonances."""
        motif = MotifFactory()
        motif_resonance = MotifResonanceFactory(motif=motif)
        MotifResonanceAssociationFactory(motif_resonance=motif_resonance)

        serializer = MotifSerializer(motif)
        data = serializer.data

        self.assertIn("resonances", data)
        self.assertEqual(len(data["resonances"]), 1)
        self.assertIn("associations", data["resonances"][0])


class MotifResonanceSerializerTest(TestCase):
    """Tests for MotifResonanceSerializer."""

    def test_serialization(self):
        """Test MotifResonanceSerializer includes associations."""
        motif_resonance = MotifResonanceFactory()
        association = ResonanceAssociationFactory(name="Shadows")
        MotifResonanceAssociationFactory(
            motif_resonance=motif_resonance,
            association=association,
        )

        serializer = MotifResonanceSerializer(motif_resonance)
        data = serializer.data

        self.assertIn("resonance_name", data)
        self.assertIn("associations", data)
        self.assertEqual(len(data["associations"]), 1)
        self.assertEqual(data["associations"][0]["association_name"], "Shadows")


class MotifResonanceAssociationSerializerTest(TestCase):
    """Tests for MotifResonanceAssociationSerializer."""

    def test_serialization(self):
        """Test MotifResonanceAssociationSerializer includes association name."""
        association = ResonanceAssociationFactory(name="Fire")
        motif_assoc = MotifResonanceAssociationFactory(association=association)

        serializer = MotifResonanceAssociationSerializer(motif_assoc)
        data = serializer.data

        self.assertEqual(data["association"], association.id)
        self.assertEqual(data["association_name"], "Fire")


class DraftAnimaRitualSerializerTest(TestCase):
    """Tests for DraftAnimaRitualSerializer."""

    def test_serialization(self):
        """Test DraftAnimaRitualSerializer includes all name fields."""
        ritual = DraftAnimaRitualFactory()

        serializer = DraftAnimaRitualSerializer(ritual)
        data = serializer.data

        self.assertIn("stat_name", data)
        self.assertIn("skill_name", data)
        self.assertIn("resonance_name", data)
        self.assertIn("description", data)

    def test_specialization_name_null_when_absent(self):
        """Test specialization_name is null when no specialization."""
        ritual = DraftAnimaRitualFactory(specialization=None)

        serializer = DraftAnimaRitualSerializer(ritual)
        data = serializer.data

        self.assertIsNone(data["specialization_name"])

    def test_specialization_name_present_when_set(self):
        """Test specialization_name is present when specialization is set."""
        from world.skills.factories import SpecializationFactory

        spec = SpecializationFactory(name="Test Spec")
        ritual = DraftAnimaRitualFactory(specialization=spec)

        serializer = DraftAnimaRitualSerializer(ritual)
        data = serializer.data

        self.assertEqual(data["specialization_name"], "Test Spec")
