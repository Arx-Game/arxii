"""Tests for magic system serializers."""

from django.test import TestCase

from world.codex.factories import CodexEntryFactory
from world.magic.factories import (
    EffectTypeFactory,
    FacetFactory,
    GiftFactory,
    MotifFactory,
    MotifResonanceAssociationFactory,
    MotifResonanceFactory,
    ResonanceModifierTypeFactory,
    RestrictionFactory,
    TechniqueFactory,
    TechniqueStyleFactory,
)
from world.magic.serializers import (
    EffectTypeSerializer,
    GiftCreateSerializer,
    GiftSerializer,
    ModifierTypeSerializer,
    MotifResonanceAssociationSerializer,
    MotifResonanceSerializer,
    MotifSerializer,
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
        self.assertIn("resonances", data)  # Full resonance data, not just IDs
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
        self.assertIn("facet_assignments", data["resonances"][0])


class MotifResonanceSerializerTest(TestCase):
    """Tests for MotifResonanceSerializer."""

    def test_serialization(self):
        """Test MotifResonanceSerializer includes facet assignments."""
        motif_resonance = MotifResonanceFactory()
        facet = FacetFactory(name="Shadows")
        MotifResonanceAssociationFactory(
            motif_resonance=motif_resonance,
            facet=facet,
        )

        serializer = MotifResonanceSerializer(motif_resonance)
        data = serializer.data

        self.assertIn("resonance_name", data)
        self.assertIn("facet_assignments", data)
        self.assertEqual(len(data["facet_assignments"]), 1)
        self.assertEqual(data["facet_assignments"][0]["facet_name"], "Shadows")


class MotifResonanceAssociationSerializerTest(TestCase):
    """Tests for MotifResonanceAssociationSerializer."""

    def test_serialization(self):
        """Test MotifResonanceAssociationSerializer includes facet name."""
        facet = FacetFactory(name="Fire")
        motif_assoc = MotifResonanceAssociationFactory(facet=facet)

        serializer = MotifResonanceAssociationSerializer(motif_assoc)
        data = serializer.data

        self.assertEqual(data["facet"], facet.id)
        self.assertEqual(data["facet_name"], "Fire")


class FacetSerializerTest(TestCase):
    """Tests for FacetSerializer."""

    def test_serialization_with_hierarchy(self):
        """Test FacetSerializer includes hierarchy info."""
        from world.magic.models import Facet
        from world.magic.serializers import FacetSerializer

        creatures = Facet.objects.create(name="Creatures")
        mammals = Facet.objects.create(name="Mammals", parent=creatures)
        wolf = Facet.objects.create(name="Wolf", parent=mammals)

        serializer = FacetSerializer(wolf)
        data = serializer.data

        self.assertEqual(data["name"], "Wolf")
        self.assertEqual(data["depth"], 2)
        self.assertEqual(data["full_path"], "Creatures > Mammals > Wolf")
        self.assertEqual(data["parent"], mammals.id)
        self.assertEqual(data["parent_name"], "Mammals")

    def test_top_level_facet(self):
        """Test serialization of top-level category."""
        from world.magic.models import Facet
        from world.magic.serializers import FacetSerializer

        creatures = Facet.objects.create(name="Creatures", description="Animals")

        serializer = FacetSerializer(creatures)
        data = serializer.data

        self.assertEqual(data["name"], "Creatures")
        self.assertEqual(data["depth"], 0)
        self.assertEqual(data["full_path"], "Creatures")
        self.assertIsNone(data["parent"])
        self.assertIsNone(data["parent_name"])


class FacetTreeSerializerTest(TestCase):
    """Tests for FacetTreeSerializer with nested children."""

    def test_nested_tree_structure(self):
        """Test that tree serializer includes nested children."""
        from world.magic.models import Facet
        from world.magic.serializers import FacetTreeSerializer

        creatures = Facet.objects.create(name="Creatures")
        mammals = Facet.objects.create(name="Mammals", parent=creatures)
        Facet.objects.create(name="Wolf", parent=mammals)
        Facet.objects.create(name="Bear", parent=mammals)

        serializer = FacetTreeSerializer(creatures)
        data = serializer.data

        self.assertEqual(data["name"], "Creatures")
        self.assertEqual(len(data["children"]), 1)  # Mammals
        self.assertEqual(data["children"][0]["name"], "Mammals")
        self.assertEqual(len(data["children"][0]["children"]), 2)  # Wolf, Bear


class CharacterFacetSerializerTest(TestCase):
    """Tests for CharacterFacetSerializer."""

    @classmethod
    def setUpTestData(cls):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import ResonanceModifierTypeFactory
        from world.magic.models import Facet

        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceModifierTypeFactory(name="Praedari")
        cls.creatures = Facet.objects.create(name="Creatures")
        cls.spider = Facet.objects.create(name="Spider", parent=cls.creatures)

    def test_serialization(self):
        """Test CharacterFacetSerializer includes all fields."""
        from world.magic.models import CharacterFacet
        from world.magic.serializers import CharacterFacetSerializer

        char_facet = CharacterFacet.objects.create(
            character=self.sheet,
            facet=self.spider,
            resonance=self.resonance,
            flavor_text="Patient predator",
        )

        serializer = CharacterFacetSerializer(char_facet)
        data = serializer.data

        self.assertEqual(data["facet"], self.spider.id)
        self.assertEqual(data["facet_name"], "Spider")
        self.assertEqual(data["facet_path"], "Creatures > Spider")
        self.assertEqual(data["resonance"], self.resonance.id)
        self.assertEqual(data["resonance_name"], "Praedari")
        self.assertEqual(data["flavor_text"], "Patient predator")


class ModifierTypeSerializerTest(TestCase):
    """Tests for ModifierTypeSerializer with codex_entry_id."""

    def test_codex_entry_id_returns_id_when_linked(self):
        """codex_entry_id returns the entry ID when modifier type has a Codex entry."""
        resonance = ResonanceModifierTypeFactory(name="Praedari")
        codex_entry = CodexEntryFactory(
            name="Praedari Codex Entry",
            modifier_type=resonance,
        )

        serializer = ModifierTypeSerializer(resonance)
        data = serializer.data

        self.assertEqual(data["codex_entry_id"], codex_entry.id)

    def test_codex_entry_id_returns_none_when_not_linked(self):
        """codex_entry_id returns None when modifier type has no Codex entry."""
        resonance = ResonanceModifierTypeFactory(name="Umbral")

        serializer = ModifierTypeSerializer(resonance)
        data = serializer.data

        self.assertIsNone(data["codex_entry_id"])

    def test_serializer_includes_all_expected_fields(self):
        """Serializer includes all expected fields."""
        resonance = ResonanceModifierTypeFactory(
            name="Praedari",
            description="The predator resonance",
        )

        serializer = ModifierTypeSerializer(resonance)
        data = serializer.data

        self.assertIn("id", data)
        self.assertIn("name", data)
        self.assertIn("category", data)
        self.assertIn("category_name", data)
        self.assertIn("description", data)
        self.assertIn("codex_entry_id", data)
        self.assertEqual(data["name"], "Praedari")
        self.assertEqual(data["category_name"], "resonance")
