"""Tests for distinction models."""

from django.db import IntegrityError
from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.distinctions.models import (
    CharacterDistinction,
    CharacterDistinctionOther,
    Distinction,
    DistinctionCategory,
    DistinctionEffect,
    DistinctionPrerequisite,
    DistinctionTag,
)
from world.distinctions.types import DistinctionOrigin, OtherStatus
from world.mechanics.factories import ModifierCategoryFactory, ModifierTypeFactory


class DistinctionCategoryTests(TestCase):
    """Test DistinctionCategory model."""

    def test_category_creation(self):
        """Test basic category creation."""
        # Use a unique slug to avoid conflict with seeded data
        category = DistinctionCategory.objects.create(
            name="Test Physical",
            slug="test-physical",
            description="Body, health, constitution",
            display_order=100,
        )
        self.assertEqual(category.name, "Test Physical")
        self.assertEqual(category.slug, "test-physical")
        self.assertEqual(category.display_order, 100)

    def test_category_str(self):
        """Test __str__ returns name."""
        # Use a unique slug to avoid conflict with seeded data
        category = DistinctionCategory.objects.create(
            name="Test Mental",
            slug="test-mental",
        )
        self.assertEqual(str(category), "Test Mental")

    def test_category_ordering(self):
        """Test categories order by display_order."""
        # Use high display_order to ensure these come after seeded categories
        cat_b = DistinctionCategory.objects.create(name="Test B", slug="test-b", display_order=102)
        cat_a = DistinctionCategory.objects.create(name="Test A", slug="test-a", display_order=101)
        # Filter to only our test categories
        categories = list(DistinctionCategory.objects.filter(slug__in=["test-a", "test-b"]))
        self.assertEqual(categories, [cat_a, cat_b])


class DistinctionTagTests(TestCase):
    """Test DistinctionTag model."""

    def test_tag_creation(self):
        """Test basic tag creation."""
        tag = DistinctionTag.objects.create(
            name="Combat Relevant",
            slug="combat-relevant",
        )
        self.assertEqual(tag.name, "Combat Relevant")
        self.assertEqual(tag.slug, "combat-relevant")

    def test_tag_str(self):
        """Test __str__ returns name."""
        tag = DistinctionTag.objects.create(name="Social", slug="social")
        self.assertEqual(str(tag), "Social")


class DistinctionTests(TestCase):
    """Test Distinction model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all tests."""
        cls.category, _ = DistinctionCategory.objects.get_or_create(
            slug="physical",
            defaults={
                "name": "Physical",
                "description": "Physical distinctions",
                "display_order": 1,
            },
        )

    def test_distinction_creation(self):
        """Test basic distinction creation with category FK."""
        distinction = Distinction.objects.create(
            name="Strong",
            slug="strong",
            description="Exceptional physical strength.",
            category=self.category,
            cost_per_rank=3,
            max_rank=1,
        )
        self.assertEqual(distinction.name, "Strong")
        self.assertEqual(distinction.slug, "strong")
        self.assertEqual(distinction.category, self.category)
        self.assertEqual(distinction.cost_per_rank, 3)
        self.assertEqual(distinction.max_rank, 1)
        self.assertTrue(distinction.is_active)

    def test_distinction_with_negative_cost(self):
        """Test disadvantage that reimburses points (negative cost)."""
        disadvantage = Distinction.objects.create(
            name="Weak",
            slug="weak",
            description="Below average strength.",
            category=self.category,
            cost_per_rank=-2,
            max_rank=1,
        )
        self.assertEqual(disadvantage.cost_per_rank, -2)
        # Calculate cost for rank 1 - should reimburse 2 points
        self.assertEqual(disadvantage.calculate_total_cost(1), -2)

    def test_distinction_ranked(self):
        """Test distinction with max_rank > 1."""
        ranked = Distinction.objects.create(
            name="Iron Will",
            slug="iron-will",
            description="Mental fortitude that can be improved.",
            category=self.category,
            cost_per_rank=2,
            max_rank=3,
        )
        self.assertEqual(ranked.max_rank, 3)
        # Cost scales with rank
        self.assertEqual(ranked.calculate_total_cost(1), 2)
        self.assertEqual(ranked.calculate_total_cost(2), 4)
        self.assertEqual(ranked.calculate_total_cost(3), 6)

    def test_distinction_variant_parent(self):
        """Test parent/child variant relationship and computed is_variant_parent."""
        parent = Distinction.objects.create(
            name="Noble Blood",
            slug="noble-blood",
            description="You have noble ancestry.",
            category=self.category,
            cost_per_rank=2,
        )
        # Before adding a variant, is_variant_parent should be False
        self.assertFalse(parent.is_variant_parent)

        variant = Distinction.objects.create(
            name="Noble Blood (Valardin)",
            slug="noble-blood-valardin",
            description="You have Valardin noble ancestry.",
            category=self.category,
            cost_per_rank=2,
            parent_distinction=parent,
        )
        # Now that a variant exists, is_variant_parent should be True
        self.assertTrue(parent.is_variant_parent)
        self.assertEqual(variant.parent_distinction, parent)
        self.assertIn(variant, parent.variants.all())

    def test_distinction_str(self):
        """Test __str__ returns name."""
        distinction = Distinction.objects.create(
            name="Quick Reflexes",
            slug="quick-reflexes",
            category=self.category,
        )
        self.assertEqual(str(distinction), "Quick Reflexes")

    def test_distinction_total_cost(self):
        """Test calculate_total_cost method."""
        distinction = Distinction.objects.create(
            name="Tough",
            slug="tough",
            category=self.category,
            cost_per_rank=5,
            max_rank=5,
        )
        # cost_per_rank * rank
        self.assertEqual(distinction.calculate_total_cost(0), 0)
        self.assertEqual(distinction.calculate_total_cost(1), 5)
        self.assertEqual(distinction.calculate_total_cost(3), 15)
        self.assertEqual(distinction.calculate_total_cost(5), 25)


class DistinctionEffectTests(TestCase):
    """Test DistinctionEffect model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all tests."""
        cls.category, _ = DistinctionCategory.objects.get_or_create(
            slug="physical",
            defaults={
                "name": "Physical",
                "description": "Physical distinctions",
                "display_order": 1,
            },
        )
        cls.distinction = Distinction.objects.create(
            name="Beautiful",
            slug="beautiful",
            description="Exceptional physical beauty.",
            category=cls.category,
            cost_per_rank=3,
            max_rank=5,
        )
        # Create modifier types for testing
        cls.stat_category = ModifierCategoryFactory(name="stat")
        cls.affinity_category = ModifierCategoryFactory(name="affinity")
        cls.allure = ModifierTypeFactory(name="Allure", category=cls.stat_category)
        cls.celestial = ModifierTypeFactory(name="Celestial", category=cls.affinity_category)

    def test_effect_with_modifier_type(self):
        """Test effect targeting a ModifierType."""
        effect = DistinctionEffect.objects.create(
            distinction=self.distinction,
            target=self.allure,
            value_per_rank=5,
            description="Adds to allure stat.",
        )
        self.assertEqual(effect.distinction, self.distinction)
        self.assertEqual(effect.target, self.allure)
        self.assertEqual(effect.target.category.name, "stat")
        self.assertEqual(effect.value_per_rank, 5)

    def test_effect_with_affinity_type(self):
        """Test effect targeting an affinity ModifierType."""
        effect = DistinctionEffect.objects.create(
            distinction=self.distinction,
            target=self.celestial,
            description="Adds to celestial affinity.",
        )
        self.assertEqual(effect.target, self.celestial)
        self.assertEqual(effect.target.category.name, "affinity")

    def test_non_linear_scaling(self):
        """Test effect with non-linear scaling_values."""
        effect = DistinctionEffect.objects.create(
            distinction=self.distinction,
            target=self.allure,
            scaling_values=[5, 10, 20, 35, 50],
            description="Non-linear scaling per rank.",
        )
        self.assertEqual(effect.get_value_at_rank(1), 5)
        self.assertEqual(effect.get_value_at_rank(3), 20)
        self.assertEqual(effect.get_value_at_rank(5), 50)

    def test_linear_scaling_fallback(self):
        """Test effect with value_per_rank linear scaling."""
        effect = DistinctionEffect.objects.create(
            distinction=self.distinction,
            target=self.allure,
            value_per_rank=5,
            description="Linear scaling per rank.",
        )
        self.assertEqual(effect.get_value_at_rank(1), 5)
        self.assertEqual(effect.get_value_at_rank(3), 15)
        self.assertEqual(effect.get_value_at_rank(5), 25)

    def test_str_representation(self):
        """Test __str__ returns distinction name and target name."""
        effect = DistinctionEffect.objects.create(
            distinction=self.distinction,
            target=self.allure,
            value_per_rank=5,
        )
        self.assertEqual(str(effect), "Beautiful: Allure")


class DistinctionPrerequisiteTests(TestCase):
    """Test DistinctionPrerequisite model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all tests."""
        cls.category, _ = DistinctionCategory.objects.get_or_create(
            slug="background",
            defaults={
                "name": "Background",
                "description": "Background distinctions",
                "display_order": 5,
            },
        )
        cls.distinction = Distinction.objects.create(
            name="Knight Errant",
            slug="knight-errant",
            description="A wandering knight seeking glory.",
            category=cls.category,
            cost_per_rank=5,
            max_rank=1,
        )

    def test_prerequisite_creation(self):
        """Test prerequisite creation with AND logic for species/distinction."""
        rule_json = {
            "AND": [
                {"type": "species", "value": "human"},
                {"type": "distinction", "slug": "noble-blood", "min_rank": 1},
            ]
        }
        prerequisite = DistinctionPrerequisite.objects.create(
            distinction=self.distinction,
            rule_json=rule_json,
            description="Must be human with noble blood.",
        )
        self.assertEqual(prerequisite.distinction, self.distinction)
        self.assertEqual(prerequisite.rule_json, rule_json)
        self.assertEqual(prerequisite.description, "Must be human with noble blood.")
        # Verify the rule_json structure
        self.assertIn("AND", prerequisite.rule_json)
        self.assertEqual(len(prerequisite.rule_json["AND"]), 2)
        self.assertEqual(prerequisite.rule_json["AND"][0]["type"], "species")
        self.assertEqual(prerequisite.rule_json["AND"][1]["type"], "distinction")
        # Verify __str__
        self.assertEqual(str(prerequisite), "Prerequisite for Knight Errant")


class MutualExclusionTests(TestCase):
    """Test symmetrical M2M mutual exclusion on Distinction."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all tests."""
        cls.category, _ = DistinctionCategory.objects.get_or_create(
            slug="physical",
            defaults={
                "name": "Physical",
                "description": "Physical distinctions",
                "display_order": 1,
            },
        )
        # Use get_or_create since migrations may have already created these
        cls.giants_blood, _ = Distinction.objects.get_or_create(
            slug="giants-blood",
            defaults={
                "name": "Giant's Blood",
                "description": "You have the blood of giants.",
                "category": cls.category,
                "cost_per_rank": 3,
                "max_rank": 1,
            },
        )
        cls.frail, _ = Distinction.objects.get_or_create(
            slug="frail",
            defaults={
                "name": "Frail",
                "description": "You are physically frail.",
                "category": cls.category,
                "cost_per_rank": -2,
                "max_rank": 1,
            },
        )

    def test_mutual_exclusion_is_symmetrical(self):
        """Adding mutual exclusion from one side makes it visible from both."""
        self.giants_blood.mutually_exclusive_with.add(self.frail)

        # Check from giants_blood side
        self.assertIn(self.frail, self.giants_blood.mutually_exclusive_with.all())

        # Check from frail side - should also show the relationship
        self.assertIn(self.giants_blood, self.frail.mutually_exclusive_with.all())

    def test_get_mutually_exclusive_method(self):
        """Test get_mutually_exclusive method returns correct distinctions."""
        self.giants_blood.mutually_exclusive_with.add(self.frail)

        excluded = self.giants_blood.get_mutually_exclusive()
        self.assertEqual(excluded.count(), 1)
        self.assertIn(self.frail, excluded)


class CharacterDistinctionTests(TestCase):
    """Test CharacterDistinction model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all tests."""
        cls.category, _ = DistinctionCategory.objects.get_or_create(
            slug="physical",
            defaults={
                "name": "Physical",
                "description": "Physical distinctions",
                "display_order": 1,
            },
        )
        cls.distinction = Distinction.objects.create(
            name="Iron Will",
            slug="iron-will",
            description="Mental fortitude.",
            category=cls.category,
            cost_per_rank=2,
            max_rank=5,
        )
        cls.character = CharacterFactory()

    def test_character_distinction_creation(self):
        """Test creating a character distinction with rank."""
        char_distinction = CharacterDistinction.objects.create(
            character=self.character,
            distinction=self.distinction,
            rank=3,
        )
        self.assertEqual(char_distinction.character, self.character)
        self.assertEqual(char_distinction.distinction, self.distinction)
        self.assertEqual(char_distinction.rank, 3)
        self.assertEqual(char_distinction.origin, DistinctionOrigin.CHARACTER_CREATION)
        self.assertFalse(char_distinction.is_temporary)
        # Verify __str__ includes rank for multi-rank distinctions
        self.assertEqual(str(char_distinction), f"Iron Will (Rank 3) on {self.character}")
        # Verify calculate_total_cost
        self.assertEqual(char_distinction.calculate_total_cost(), 6)

    def test_character_distinction_with_notes(self):
        """Test character distinction with player notes."""
        notes = "Gained through surviving the siege of Arx."
        char_distinction = CharacterDistinction.objects.create(
            character=self.character,
            distinction=self.distinction,
            rank=1,
            notes=notes,
        )
        self.assertEqual(char_distinction.notes, notes)
        self.assertEqual(len(char_distinction.notes), 42)

    def test_character_distinction_temporary(self):
        """Test temporary distinction from gameplay."""
        char_distinction = CharacterDistinction.objects.create(
            character=self.character,
            distinction=self.distinction,
            rank=1,
            origin=DistinctionOrigin.GAMEPLAY,
            is_temporary=True,
            source_description="Granted by magical blessing for 3 months.",
        )
        self.assertEqual(char_distinction.origin, DistinctionOrigin.GAMEPLAY)
        self.assertTrue(char_distinction.is_temporary)
        self.assertEqual(
            char_distinction.source_description,
            "Granted by magical blessing for 3 months.",
        )

    def test_character_distinction_unique_together(self):
        """Test that a character cannot have the same distinction twice."""
        CharacterDistinction.objects.create(
            character=self.character,
            distinction=self.distinction,
            rank=1,
        )
        with self.assertRaises(IntegrityError):
            CharacterDistinction.objects.create(
                character=self.character,
                distinction=self.distinction,
                rank=2,
            )


class CharacterDistinctionOtherTests(TestCase):
    """Test CharacterDistinctionOther model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all tests."""
        cls.category, _ = DistinctionCategory.objects.get_or_create(
            slug="background",
            defaults={
                "name": "Background",
                "description": "Background distinctions",
                "display_order": 5,
            },
        )
        cls.addiction_parent = Distinction.objects.create(
            name="Addiction",
            slug="addiction",
            description="Character has an addiction.",
            category=cls.category,
            cost_per_rank=-2,
            allow_other=True,
        )
        cls.character = CharacterFactory()

    def test_other_creation(self):
        """Test creating an 'Other' entry with freeform text."""
        other_entry = CharacterDistinctionOther.objects.create(
            character=self.character,
            parent_distinction=self.addiction_parent,
            freeform_text="Caffeine",
        )
        self.assertEqual(other_entry.character, self.character)
        self.assertEqual(other_entry.parent_distinction, self.addiction_parent)
        self.assertEqual(other_entry.freeform_text, "Caffeine")
        self.assertEqual(other_entry.status, OtherStatus.PENDING_REVIEW)
        self.assertIsNone(other_entry.staff_mapped_distinction)
        self.assertEqual(str(other_entry), "'Caffeine' for Addiction")

    def test_other_mapped_to_distinction(self):
        """Test 'Other' entry mapped to an existing distinction by staff."""
        caffeine_addiction = Distinction.objects.create(
            name="Addiction (Caffeine)",
            slug="addiction-caffeine",
            description="Addicted to caffeine.",
            category=self.category,
            cost_per_rank=-2,
            parent_distinction=self.addiction_parent,
        )
        other_entry = CharacterDistinctionOther.objects.create(
            character=self.character,
            parent_distinction=self.addiction_parent,
            freeform_text="Caffeine",
            staff_mapped_distinction=caffeine_addiction,
            status=OtherStatus.MAPPED,
        )
        self.assertEqual(other_entry.status, OtherStatus.MAPPED)
        self.assertEqual(other_entry.staff_mapped_distinction, caffeine_addiction)
