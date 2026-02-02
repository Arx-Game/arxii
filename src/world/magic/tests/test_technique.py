"""Tests for the Technique model."""

from django.test import TestCase

from world.magic.factories import (
    BinaryEffectTypeFactory,
    EffectTypeFactory,
    GiftFactory,
    RestrictionFactory,
    TechniqueFactory,
    TechniqueStyleFactory,
)
from world.magic.models import Technique


class TechniqueModelTests(TestCase):
    """Tests for the Technique model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.gift = GiftFactory(name="Shadow Majesty")
        cls.style = TechniqueStyleFactory(name="Test Manifestation")
        cls.effect_type = EffectTypeFactory(name="Test Attack", base_power=10)
        cls.restriction1 = RestrictionFactory(name="Test Touch Range", power_bonus=10)
        cls.restriction2 = RestrictionFactory(name="Test Line of Sight", power_bonus=5)

        cls.technique = Technique.objects.create(
            name="Shadow Bolt",
            gift=cls.gift,
            style=cls.style,
            effect_type=cls.effect_type,
            level=5,
            anima_cost=3,
            description="Launch a bolt of shadow energy.",
        )
        cls.technique.restrictions.add(cls.restriction1, cls.restriction2)

    def test_technique_creation(self):
        """Test creation of a technique with all relationships."""
        self.assertEqual(self.technique.name, "Shadow Bolt")
        self.assertEqual(self.technique.gift, self.gift)
        self.assertEqual(self.technique.style, self.style)
        self.assertEqual(self.technique.effect_type, self.effect_type)
        self.assertEqual(self.technique.level, 5)
        self.assertEqual(self.technique.anima_cost, 3)
        self.assertEqual(self.technique.description, "Launch a bolt of shadow energy.")

    def test_technique_str(self):
        """Test string representation."""
        self.assertEqual(str(self.technique), "Shadow Bolt (Shadow Majesty)")

    def test_technique_restrictions(self):
        """Test that technique can have multiple restrictions."""
        self.assertEqual(self.technique.restrictions.count(), 2)
        self.assertIn(self.restriction1, self.technique.restrictions.all())
        self.assertIn(self.restriction2, self.technique.restrictions.all())

    def test_tier_level_1(self):
        """Test tier at level 1."""
        self.technique.level = 1
        self.technique.save()
        self.assertEqual(self.technique.tier, 1)

    def test_tier_level_5(self):
        """Test tier at level 5 (upper bound of T1)."""
        self.technique.level = 5
        self.technique.save()
        self.assertEqual(self.technique.tier, 1)

    def test_tier_level_6(self):
        """Test tier at level 6 (lower bound of T2)."""
        self.technique.level = 6
        self.technique.save()
        self.assertEqual(self.technique.tier, 2)

    def test_tier_level_10(self):
        """Test tier at level 10 (upper bound of T2)."""
        self.technique.level = 10
        self.technique.save()
        self.assertEqual(self.technique.tier, 2)

    def test_tier_level_11(self):
        """Test tier at level 11 (lower bound of T3)."""
        self.technique.level = 11
        self.technique.save()
        self.assertEqual(self.technique.tier, 3)

    def test_tier_level_15(self):
        """Test tier at level 15 (upper bound of T3)."""
        self.technique.level = 15
        self.technique.save()
        self.assertEqual(self.technique.tier, 3)

    def test_tier_level_16(self):
        """Test tier at level 16 (lower bound of T4)."""
        self.technique.level = 16
        self.technique.save()
        self.assertEqual(self.technique.tier, 4)

    def test_tier_level_20(self):
        """Test tier at level 20 (upper bound of T4)."""
        self.technique.level = 20
        self.technique.save()
        self.assertEqual(self.technique.tier, 4)

    def test_tier_level_21(self):
        """Test tier at level 21+ is T5."""
        self.technique.level = 21
        self.technique.save()
        self.assertEqual(self.technique.tier, 5)

    def test_tier_level_100(self):
        """Test tier at very high level is still T5."""
        self.technique.level = 100
        self.technique.save()
        self.assertEqual(self.technique.tier, 5)

    def test_calculated_power_with_restrictions(self):
        """Test calculated_power sums base_power and restriction bonuses."""
        # base_power=10, restriction1=10, restriction2=5
        expected = 10 + 10 + 5
        self.assertEqual(self.technique.calculated_power, expected)

    def test_calculated_power_no_restrictions(self):
        """Test calculated_power with no restrictions returns base_power."""
        technique = Technique.objects.create(
            name="Simple Bolt",
            gift=self.gift,
            style=self.style,
            effect_type=self.effect_type,
            level=1,
            anima_cost=1,
        )
        self.assertEqual(technique.calculated_power, 10)  # Just base_power

    def test_calculated_power_returns_none_for_non_scaled_effects(self):
        """Test calculated_power returns None for binary effect types."""
        binary_effect = BinaryEffectTypeFactory(name="Teleport")
        technique = Technique.objects.create(
            name="Shadow Step",
            gift=self.gift,
            style=self.style,
            effect_type=binary_effect,
            level=1,
            anima_cost=2,
        )
        self.assertIsNone(technique.calculated_power)

    def test_calculated_power_with_null_base_power(self):
        """Test calculated_power handles null base_power gracefully."""
        # Effect type with has_power_scaling=True but base_power=None
        effect = EffectTypeFactory(name="Scaling No Base", base_power=None)
        technique = Technique.objects.create(
            name="No Base",
            gift=self.gift,
            style=self.style,
            effect_type=effect,
            level=1,
            anima_cost=1,
        )
        technique.restrictions.add(self.restriction1)  # +10
        self.assertEqual(technique.calculated_power, 10)  # 0 + 10

    def test_default_level(self):
        """Test that level defaults to 1."""
        technique = Technique.objects.create(
            name="Default Level",
            gift=self.gift,
            style=self.style,
            effect_type=self.effect_type,
            anima_cost=1,
        )
        self.assertEqual(technique.level, 1)

    def test_name_not_unique(self):
        """Test that name is not unique - different characters can have same name."""
        gift2 = GiftFactory(name="Fire Lord")
        technique2 = Technique.objects.create(
            name="Shadow Bolt",  # Same name as existing
            gift=gift2,
            style=self.style,
            effect_type=self.effect_type,
            level=1,
            anima_cost=2,
        )
        self.assertEqual(technique2.name, "Shadow Bolt")
        self.assertNotEqual(technique2.pk, self.technique.pk)

    def test_gift_cascade_delete(self):
        """Test that deleting a gift cascades to delete techniques."""
        technique_pk = self.technique.pk
        self.gift.delete()
        self.assertFalse(Technique.objects.filter(pk=technique_pk).exists())

    def test_style_protect_delete(self):
        """Test that style is protected from deletion if techniques exist."""
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            self.style.delete()

    def test_effect_type_protect_delete(self):
        """Test that effect_type is protected from deletion if techniques exist."""
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            self.effect_type.delete()

    def test_gift_related_name(self):
        """Test that Gift has techniques related name."""
        self.assertIn(self.technique, self.gift.techniques.all())

    def test_style_related_name(self):
        """Test that TechniqueStyle has techniques related name."""
        self.assertIn(self.technique, self.style.techniques.all())

    def test_effect_type_related_name(self):
        """Test that EffectType has techniques related name."""
        self.assertIn(self.technique, self.effect_type.techniques.all())

    def test_restriction_related_name(self):
        """Test that Restriction has techniques related name."""
        self.assertIn(self.technique, self.restriction1.techniques.all())


class TechniqueFactoryTests(TestCase):
    """Tests for the TechniqueFactory."""

    def test_factory_creates_technique(self):
        """Test that factory creates a valid Technique."""
        technique = TechniqueFactory()
        self.assertIsInstance(technique, Technique)
        self.assertTrue(technique.name)
        self.assertIsNotNone(technique.gift)
        self.assertIsNotNone(technique.style)
        self.assertIsNotNone(technique.effect_type)

    def test_factory_with_restrictions(self):
        """Test factory can add restrictions via post_generation."""
        restriction1 = RestrictionFactory(name="Factory Restriction 1")
        restriction2 = RestrictionFactory(name="Factory Restriction 2")
        technique = TechniqueFactory(restrictions=[restriction1, restriction2])
        self.assertEqual(technique.restrictions.count(), 2)
        self.assertIn(restriction1, technique.restrictions.all())
        self.assertIn(restriction2, technique.restrictions.all())

    def test_factory_does_not_use_get_or_create(self):
        """Test factory creates new instances each time (not a lookup table)."""
        technique1 = TechniqueFactory(name="Same Name")
        technique2 = TechniqueFactory(name="Same Name")
        self.assertNotEqual(technique1.pk, technique2.pk)

    def test_factory_with_custom_gift(self):
        """Test factory accepts custom gift."""
        gift = GiftFactory(name="Custom Gift")
        technique = TechniqueFactory(gift=gift)
        self.assertEqual(technique.gift, gift)

    def test_factory_with_custom_style(self):
        """Test factory accepts custom style."""
        style = TechniqueStyleFactory(name="Custom Style")
        technique = TechniqueFactory(style=style)
        self.assertEqual(technique.style, style)

    def test_factory_with_custom_effect_type(self):
        """Test factory accepts custom effect type."""
        effect_type = EffectTypeFactory(name="Custom Effect")
        technique = TechniqueFactory(effect_type=effect_type)
        self.assertEqual(technique.effect_type, effect_type)

    def test_factory_default_level(self):
        """Test factory sets default level."""
        technique = TechniqueFactory()
        self.assertEqual(technique.level, 1)

    def test_factory_default_anima_cost(self):
        """Test factory sets default anima_cost."""
        technique = TechniqueFactory()
        self.assertEqual(technique.anima_cost, 2)
