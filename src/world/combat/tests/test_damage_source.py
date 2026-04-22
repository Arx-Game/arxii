"""Tests for world.combat.damage_source.classify_source (Task 29)."""

from unittest.mock import MagicMock

from django.test import TestCase

from flows.events.payloads import DamageSource
from world.combat.damage_source import classify_source


class ClassifySourceNoneTest(TestCase):
    """classify_source(None) returns a DamageSource with fallback type."""

    def test_none_returns_environment_type(self) -> None:
        result = classify_source(None)
        self.assertIsInstance(result, DamageSource)
        # None source means no identifiable origin — maps to 'environment' fallback
        self.assertEqual(result.type, "environment")
        self.assertIsNone(result.ref)


class ClassifySourceCharacterTest(TestCase):
    """classify_source with a Character typeclass instance."""

    def test_character_returns_character_type(self) -> None:
        from evennia_extensions.factories import CharacterFactory

        char = CharacterFactory()
        result = classify_source(char)
        self.assertIsInstance(result, DamageSource)
        self.assertEqual(result.type, "character")
        self.assertIs(result.ref, char)


class ClassifySourceUnknownObjectTest(TestCase):
    """classify_source with an unrecognised object returns item type."""

    def test_unknown_object_returns_item_type(self) -> None:
        obj = MagicMock(spec=object)
        result = classify_source(obj)
        self.assertIsInstance(result, DamageSource)
        # Fallback for unrecognised source types
        self.assertEqual(result.type, "item")
        self.assertIs(result.ref, obj)

    def test_plain_string_returns_item_type(self) -> None:
        result = classify_source("fire trap")
        self.assertEqual(result.type, "item")
        self.assertEqual(result.ref, "fire trap")
