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
    DistinctionMutualExclusion,
    DistinctionPrerequisite,
    DistinctionTag,
)
from world.distinctions.types import DistinctionOrigin, EffectType, OtherStatus


class DistinctionCategoryTests(TestCase):
    """Test DistinctionCategory model."""

    def test_category_creation(self):
        """Test basic category creation."""
        category = DistinctionCategory.objects.create(
            name="Physical",
            slug="physical",
            description="Body, health, constitution",
            display_order=1,
        )
        self.assertEqual(category.name, "Physical")
        self.assertEqual(category.slug, "physical")
        self.assertEqual(category.display_order, 1)

    def test_category_str(self):
        """Test __str__ returns name."""
        category = DistinctionCategory.objects.create(
            name="Mental",
            slug="mental",
        )
        self.assertEqual(str(category), "Mental")

    def test_category_ordering(self):
        """Test categories order by display_order."""
        cat_b = DistinctionCategory.objects.create(name="B", slug="b", display_order=2)
        cat_a = DistinctionCategory.objects.create(name="A", slug="a", display_order=1)
        categories = list(DistinctionCategory.objects.all())
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
        cls.category = DistinctionCategory.objects.create(
            name="Physical",
            slug="physical",
            description="Physical distinctions",
            display_order=1,
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
        """Test parent/child variant relationship."""
        parent = Distinction.objects.create(
            name="Noble Blood",
            slug="noble-blood",
            description="You have noble ancestry.",
            category=self.category,
            cost_per_rank=2,
            is_variant_parent=True,
        )
        variant = Distinction.objects.create(
            name="Noble Blood (Valardin)",
            slug="noble-blood-valardin",
            description="You have Valardin noble ancestry.",
            category=self.category,
            cost_per_rank=2,
            parent_distinction=parent,
        )
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
        cls.category = DistinctionCategory.objects.create(
            name="Physical",
            slug="physical",
            description="Physical distinctions",
            display_order=1,
        )
        cls.distinction = Distinction.objects.create(
            name="Beautiful",
            slug="beautiful",
            description="Exceptional physical beauty.",
            category=cls.category,
            cost_per_rank=3,
            max_rank=5,
        )

    def test_stat_modifier_effect(self):
        """Test effect with STAT_MODIFIER type targeting a stat."""
        effect = DistinctionEffect.objects.create(
            distinction=self.distinction,
            effect_type=EffectType.STAT_MODIFIER,
            target="allure",
            value_per_rank=5,
            description="Adds to allure stat.",
        )
        self.assertEqual(effect.distinction, self.distinction)
        self.assertEqual(effect.effect_type, EffectType.STAT_MODIFIER)
        self.assertEqual(effect.target, "allure")
        self.assertEqual(effect.value_per_rank, 5)

    def test_affinity_modifier_effect(self):
        """Test effect with AFFINITY_MODIFIER type targeting an affinity."""
        effect = DistinctionEffect.objects.create(
            distinction=self.distinction,
            effect_type=EffectType.AFFINITY_MODIFIER,
            target="celestial",
            description="Adds to celestial affinity.",
        )
        self.assertEqual(effect.effect_type, EffectType.AFFINITY_MODIFIER)
        self.assertEqual(effect.target, "celestial")

    def test_code_handled_effect(self):
        """Test effect with CODE_HANDLED type using slug_reference."""
        effect = DistinctionEffect.objects.create(
            distinction=self.distinction,
            effect_type=EffectType.CODE_HANDLED,
            slug_reference="never-dirty",
            description="Character's appearance never gets dirty.",
        )
        self.assertEqual(effect.effect_type, EffectType.CODE_HANDLED)
        self.assertEqual(effect.slug_reference, "never-dirty")

    def test_non_linear_scaling(self):
        """Test effect with non-linear scaling_values."""
        effect = DistinctionEffect.objects.create(
            distinction=self.distinction,
            effect_type=EffectType.STAT_MODIFIER,
            target="allure",
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
            effect_type=EffectType.STAT_MODIFIER,
            target="allure",
            value_per_rank=5,
            description="Linear scaling per rank.",
        )
        self.assertEqual(effect.get_value_at_rank(1), 5)
        self.assertEqual(effect.get_value_at_rank(3), 15)
        self.assertEqual(effect.get_value_at_rank(5), 25)

    def test_str_representation(self):
        """Test __str__ returns distinction name and effect type display."""
        effect = DistinctionEffect.objects.create(
            distinction=self.distinction,
            effect_type=EffectType.STAT_MODIFIER,
            target="allure",
            value_per_rank=5,
        )
        self.assertEqual(str(effect), "Beautiful: Stat Modifier")


class DistinctionPrerequisiteTests(TestCase):
    """Test DistinctionPrerequisite model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all tests."""
        cls.category = DistinctionCategory.objects.create(
            name="Background",
            slug="background",
            description="Background distinctions",
            display_order=1,
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


class DistinctionMutualExclusionTests(TestCase):
    """Test DistinctionMutualExclusion model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all tests."""
        cls.category = DistinctionCategory.objects.create(
            name="Physical",
            slug="physical",
            description="Physical distinctions",
            display_order=1,
        )
        cls.giants_blood = Distinction.objects.create(
            name="Giant's Blood",
            slug="giants-blood",
            description="You have the blood of giants.",
            category=cls.category,
            cost_per_rank=3,
            max_rank=1,
        )
        cls.frail = Distinction.objects.create(
            name="Frail",
            slug="frail",
            description="You are physically frail.",
            category=cls.category,
            cost_per_rank=-2,
            max_rank=1,
        )

    def test_mutual_exclusion_creation(self):
        """Test creating a mutual exclusion pair."""
        exclusion = DistinctionMutualExclusion.objects.create(
            distinction_a=self.giants_blood,
            distinction_b=self.frail,
        )
        self.assertEqual(exclusion.distinction_a, self.giants_blood)
        self.assertEqual(exclusion.distinction_b, self.frail)
        self.assertEqual(str(exclusion), "Giant's Blood <-> Frail")

    def test_get_excluded_for(self):
        """Test get_excluded_for returns the other side of exclusion from both directions."""
        DistinctionMutualExclusion.objects.create(
            distinction_a=self.giants_blood,
            distinction_b=self.frail,
        )
        # Check from giants_blood side
        excluded_for_giants = DistinctionMutualExclusion.get_excluded_for(self.giants_blood)
        self.assertEqual(len(excluded_for_giants), 1)
        self.assertIn(self.frail, excluded_for_giants)

        # Check from frail side
        excluded_for_frail = DistinctionMutualExclusion.get_excluded_for(self.frail)
        self.assertEqual(len(excluded_for_frail), 1)
        self.assertIn(self.giants_blood, excluded_for_frail)


class CharacterDistinctionTests(TestCase):
    """Test CharacterDistinction model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all tests."""
        cls.category = DistinctionCategory.objects.create(
            name="Physical",
            slug="physical",
            description="Physical distinctions",
            display_order=1,
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
        cls.category = DistinctionCategory.objects.create(
            name="Background",
            slug="background",
            description="Background distinctions",
            display_order=1,
        )
        cls.addiction_parent = Distinction.objects.create(
            name="Addiction",
            slug="addiction",
            description="Character has an addiction.",
            category=cls.category,
            cost_per_rank=-2,
            is_variant_parent=True,
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
