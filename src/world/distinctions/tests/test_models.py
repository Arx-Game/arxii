"""Tests for distinction models."""

from django.test import TestCase

from world.distinctions.models import (
    Distinction,
    DistinctionCategory,
    DistinctionEffect,
    DistinctionPrerequisite,
    DistinctionTag,
)
from world.distinctions.types import EffectType


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
