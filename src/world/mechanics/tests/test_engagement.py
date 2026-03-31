"""Tests for CharacterEngagement model."""

from django.db import IntegrityError
from django.test import TestCase

from world.mechanics.constants import EngagementType
from world.mechanics.factories import CharacterEngagementFactory


class TestCharacterEngagement(TestCase):
    """Tests for the CharacterEngagement model."""

    def test_create_engagement(self) -> None:
        """Verify defaults: escalation=0, modifiers=0."""
        engagement = CharacterEngagementFactory()
        self.assertEqual(engagement.escalation_level, 0)
        self.assertEqual(engagement.intensity_modifier, 0)
        self.assertEqual(engagement.control_modifier, 0)
        self.assertEqual(engagement.engagement_type, EngagementType.CHALLENGE)
        self.assertIsNotNone(engagement.started_at)

    def test_one_to_one_constraint(self) -> None:
        """Verify IntegrityError on duplicate character."""
        engagement = CharacterEngagementFactory()
        with self.assertRaises(IntegrityError):
            CharacterEngagementFactory(character=engagement.character)

    def test_delete_clears_process_state(self) -> None:
        """Verify delete removes the record."""
        from world.mechanics.models import CharacterEngagement

        engagement = CharacterEngagementFactory()
        char = engagement.character
        engagement.delete()
        self.assertFalse(CharacterEngagement.objects.filter(character=char).exists())

    def test_str_representation(self) -> None:
        """Verify display name in __str__."""
        engagement = CharacterEngagementFactory(
            engagement_type=EngagementType.COMBAT,
        )
        result = str(engagement)
        self.assertIn(str(engagement.character), result)
        self.assertIn("Combat", result)
