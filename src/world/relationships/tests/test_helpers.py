"""Tests for relationship helper functions."""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.relationships.helpers import get_relationship_tier


class GetRelationshipTierTests(TestCase):
    """Tests for get_relationship_tier stub."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.char_a = CharacterFactory()
        cls.char_b = CharacterFactory()

    def test_returns_zero_stub(self) -> None:
        """Stub always returns 0 until relationship tiers are defined."""
        tier = get_relationship_tier(self.char_a, self.char_b)
        self.assertEqual(tier, 0)

    def test_returns_int(self) -> None:
        """Return type is int."""
        tier = get_relationship_tier(self.char_a, self.char_b)
        self.assertIsInstance(tier, int)
