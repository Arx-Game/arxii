"""Tests for mechanics models."""

from django.db import IntegrityError
from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.mechanics.factories import (
    CharacterModifierFactory,
    ModifierCategoryFactory,
    ModifierTypeFactory,
)
from world.mechanics.models import CharacterModifier, ModifierCategory, ModifierType


class ModifierCategoryTests(TestCase):
    """Test ModifierCategory model."""

    def test_category_str(self):
        """Test __str__ returns name."""
        category = ModifierCategoryFactory(name="TestStat")
        self.assertEqual(str(category), "TestStat")

    def test_category_unique_name(self):
        """Test that category names must be unique."""
        ModifierCategoryFactory(name="UniqueName")
        with self.assertRaises(IntegrityError):
            ModifierCategory.objects.create(name="UniqueName", display_order=99)

    def test_category_ordering(self):
        """Test categories order by display_order then name."""
        cat_b = ModifierCategoryFactory(name="CategoryB", display_order=102)
        cat_a = ModifierCategoryFactory(name="CategoryA", display_order=101)
        categories = list(ModifierCategory.objects.filter(name__in=["CategoryA", "CategoryB"]))
        self.assertEqual(categories, [cat_a, cat_b])


class ModifierTypeTests(TestCase):
    """Test ModifierType model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all tests."""
        cls.category = ModifierCategoryFactory(name="TestCategory")

    def test_type_str(self):
        """Test __str__ returns name with category."""
        modifier_type = ModifierTypeFactory(name="TestType", category=self.category)
        self.assertEqual(str(modifier_type), "TestType (TestCategory)")

    def test_type_unique_together(self):
        """Test that name must be unique within category."""
        ModifierTypeFactory(name="DuplicateName", category=self.category)
        with self.assertRaises(IntegrityError):
            ModifierType.objects.create(
                name="DuplicateName", category=self.category, display_order=99
            )

    def test_type_same_name_different_category(self):
        """Test that same name is allowed in different categories."""
        other_category = ModifierCategoryFactory(name="OtherCategory")
        ModifierTypeFactory(name="SameName", category=self.category)
        # This should succeed - same name, different category
        modifier_type = ModifierTypeFactory(name="SameName", category=other_category)
        self.assertEqual(modifier_type.name, "SameName")
        self.assertEqual(modifier_type.category, other_category)

    def test_type_default_active(self):
        """Test that is_active defaults to True."""
        modifier_type = ModifierTypeFactory(category=self.category)
        self.assertTrue(modifier_type.is_active)


class CharacterModifierTests(TestCase):
    """Test CharacterModifier model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all tests."""
        cls.character = CharacterFactory()
        cls.category = ModifierCategoryFactory(name="CharModCategory")
        cls.modifier_type = ModifierTypeFactory(name="TestModifier", category=cls.category)

    def test_modifier_str_no_source(self):
        """Test __str__ with no source set returns 'unknown' source."""
        modifier = CharacterModifier.objects.create(
            character=self.character, modifier_type=self.modifier_type, value=10
        )
        expected = f"{self.character} TestModifier: +10 (unknown)"
        self.assertEqual(str(modifier), expected)

    def test_modifier_str_negative_value(self):
        """Test __str__ with negative value shows minus sign."""
        modifier = CharacterModifier.objects.create(
            character=self.character, modifier_type=self.modifier_type, value=-5
        )
        expected = f"{self.character} TestModifier: -5 (unknown)"
        self.assertEqual(str(modifier), expected)

    def test_modifier_str_with_distinction_source(self):
        """Test __str__ with distinction source."""
        # Create a CharacterDistinction to use as source
        from world.distinctions.factories import (
            CharacterDistinctionFactory,
            DistinctionFactory,
        )

        distinction = DistinctionFactory()
        char_distinction = CharacterDistinctionFactory(
            character=self.character, distinction=distinction
        )
        modifier = CharacterModifier.objects.create(
            character=self.character,
            modifier_type=self.modifier_type,
            value=5,
            source_distinction=char_distinction,
        )
        expected = f"{self.character} TestModifier: +5 (distinction:{char_distinction.id})"
        self.assertEqual(str(modifier), expected)

    def test_modifier_source_tracking_fields_nullable(self):
        """Test that source fields can be null."""
        modifier = CharacterModifier.objects.create(
            character=self.character, modifier_type=self.modifier_type, value=1
        )
        self.assertIsNone(modifier.source_distinction)
        self.assertIsNone(modifier.source_condition)

    def test_modifier_expires_at_nullable(self):
        """Test that expires_at can be null for permanent modifiers."""
        modifier = CharacterModifier.objects.create(
            character=self.character, modifier_type=self.modifier_type, value=1
        )
        self.assertIsNone(modifier.expires_at)

    def test_modifier_created_at_auto_set(self):
        """Test that created_at is automatically set."""
        modifier = CharacterModifier.objects.create(
            character=self.character, modifier_type=self.modifier_type, value=1
        )
        self.assertIsNotNone(modifier.created_at)

    def test_modifier_factory(self):
        """Test CharacterModifierFactory creates valid instance."""
        modifier = CharacterModifierFactory()
        self.assertIsNotNone(modifier.character)
        self.assertIsNotNone(modifier.modifier_type)
        self.assertIsNotNone(modifier.value)
