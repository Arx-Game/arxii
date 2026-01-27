"""Tests for mechanics models."""

from django.db import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.mechanics.factories import (
    CharacterModifierFactory,
    ModifierCategoryFactory,
    ModifierSourceFactory,
    ModifierTypeFactory,
)
from world.mechanics.models import (
    CharacterModifier,
    ModifierCategory,
    ModifierSource,
    ModifierType,
)


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


class ModifierSourceTests(TestCase):
    """Test ModifierSource model."""

    def test_source_str_unknown(self):
        """Test __str__ with no source set returns 'Unknown'."""
        source = ModifierSourceFactory()
        self.assertEqual(str(source), "Unknown")

    def test_source_str_with_distinction(self):
        """Test __str__ with distinction source."""
        from world.distinctions.factories import (
            CharacterDistinctionFactory,
            DistinctionEffectFactory,
        )

        effect = DistinctionEffectFactory()
        char_distinction = CharacterDistinctionFactory(distinction=effect.distinction)
        source = ModifierSource.objects.create(
            distinction_effect=effect, character_distinction=char_distinction
        )
        self.assertIn("Distinction:", str(source))

    def test_source_modifier_type_from_distinction_effect(self):
        """Test modifier_type property returns effect target."""
        from world.distinctions.factories import DistinctionEffectFactory

        effect = DistinctionEffectFactory()
        source = ModifierSource.objects.create(distinction_effect=effect)
        self.assertEqual(source.modifier_type, effect.target)

    def test_source_modifier_type_null_for_unknown(self):
        """Test modifier_type property returns None for unknown source."""
        source = ModifierSourceFactory()
        self.assertIsNone(source.modifier_type)

    def test_source_type_property_distinction(self):
        """Test source_type property returns 'distinction' for distinction sources."""
        from world.distinctions.factories import DistinctionEffectFactory

        effect = DistinctionEffectFactory()
        source = ModifierSource.objects.create(distinction_effect=effect)
        self.assertEqual(source.source_type, "distinction")

    def test_source_type_property_unknown(self):
        """Test source_type property returns 'unknown' for empty sources."""
        source = ModifierSourceFactory()
        self.assertEqual(source.source_type, "unknown")


class CharacterModifierTests(TestCase):
    """Test CharacterModifier model.

    Note: modifier_type is now a property derived from source.distinction_effect.target.
    Tests must create sources with valid distinction_effect to get a modifier_type.
    """

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all tests."""
        from world.distinctions.factories import (
            CharacterDistinctionFactory,
            DistinctionEffectFactory,
        )

        cls.sheet = CharacterSheetFactory()

        # Create a distinction effect with a known modifier type
        cls.effect = DistinctionEffectFactory()
        cls.char_distinction = CharacterDistinctionFactory(
            character=cls.sheet.character, distinction=cls.effect.distinction
        )
        cls.source = ModifierSource.objects.create(
            distinction_effect=cls.effect, character_distinction=cls.char_distinction
        )
        # For tests that need unknown source
        cls.unknown_source = ModifierSourceFactory()

    def test_modifier_str(self):
        """Test __str__ returns formatted string with source."""
        modifier = CharacterModifier.objects.create(
            character=self.sheet,
            value=10,
            source=self.source,
        )
        # modifier_type comes from source.distinction_effect.target
        self.assertIn(self.effect.target.name, str(modifier))
        self.assertIn("+10", str(modifier))
        self.assertIn("Distinction:", str(modifier))

    def test_modifier_str_negative_value(self):
        """Test __str__ with negative value shows minus sign."""
        modifier = CharacterModifier.objects.create(
            character=self.sheet,
            value=-5,
            source=self.source,
        )
        self.assertIn("-5", str(modifier))

    def test_modifier_str_with_unknown_source(self):
        """Test __str__ with unknown source shows 'Unknown'."""
        modifier = CharacterModifier.objects.create(
            character=self.sheet,
            value=5,
            source=self.unknown_source,
        )
        self.assertIn("Unknown", str(modifier))

    def test_modifier_type_property_from_source(self):
        """Test modifier_type property returns source.distinction_effect.target."""
        modifier = CharacterModifier.objects.create(
            character=self.sheet,
            value=5,
            source=self.source,
        )
        self.assertEqual(modifier.modifier_type, self.effect.target)

    def test_modifier_type_property_none_for_unknown_source(self):
        """Test modifier_type property returns None for unknown source."""
        modifier = CharacterModifier.objects.create(
            character=self.sheet,
            value=5,
            source=self.unknown_source,
        )
        self.assertIsNone(modifier.modifier_type)

    def test_modifier_expires_at_nullable(self):
        """Test that expires_at can be null for permanent modifiers."""
        modifier = CharacterModifier.objects.create(
            character=self.sheet,
            value=1,
            source=self.source,
        )
        self.assertIsNone(modifier.expires_at)

    def test_modifier_created_at_auto_set(self):
        """Test that created_at is automatically set."""
        modifier = CharacterModifier.objects.create(
            character=self.sheet,
            value=1,
            source=self.source,
        )
        self.assertIsNotNone(modifier.created_at)

    def test_modifier_factory(self):
        """Test CharacterModifierFactory creates valid instance with modifier_type."""
        modifier = CharacterModifierFactory()
        self.assertIsNotNone(modifier.character)
        # modifier_type is now a property from source
        self.assertIsNotNone(modifier.modifier_type)
        self.assertIsNotNone(modifier.value)
        self.assertIsNotNone(modifier.source)
        self.assertIsNotNone(modifier.source.distinction_effect)
