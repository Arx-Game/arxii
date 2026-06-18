"""Tests for relationship helper functions."""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipTierFactory,
    RelationshipTrackFactory,
    RelationshipTrackProgressFactory,
)
from world.relationships.helpers import get_relationship_tier


class GetRelationshipTierTests(TestCase):
    """Tests for get_relationship_tier."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        # bare ObjectDB characters with no CharacterSheet — for no-sheet edge cases
        cls.char_a = CharacterFactory()
        cls.char_b = CharacterFactory()
        # Characters that have CharacterSheets (needed for relationship lookups)
        cls.sheet_a = CharacterSheetFactory()
        cls.sheet_b = CharacterSheetFactory()

    def test_returns_zero_without_relationship(self) -> None:
        """Returns 0 when no relationship exists between the characters."""
        self.assertEqual(get_relationship_tier(self.sheet_a.character, self.sheet_b.character), 0)

    def test_returns_zero_when_character_has_no_sheet(self) -> None:
        """Returns 0 when a character has no CharacterSheet attached."""
        self.assertEqual(get_relationship_tier(self.char_a, self.char_b), 0)

    def test_returns_int(self) -> None:
        """Return type is int."""
        tier = get_relationship_tier(self.char_a, self.char_b)
        self.assertIsInstance(tier, int)

    def test_returns_tier_from_developed_points(self) -> None:
        """Returns the highest crossed tier_number based on developed points."""
        track = RelationshipTrackFactory()
        # tier_number=1 requires 10 points; tier_number=2 requires 20 points
        RelationshipTierFactory(track=track, tier_number=1, point_threshold=10)
        RelationshipTierFactory(track=track, tier_number=2, point_threshold=20)
        rel = CharacterRelationshipFactory(
            source=self.sheet_a,
            target=self.sheet_b,
        )
        # 25 developed points — crosses tier 1 (10) and tier 2 (20)
        RelationshipTrackProgressFactory(
            relationship=rel,
            track=track,
            capacity=25,
            developed_points=25,
        )
        result = get_relationship_tier(self.sheet_a.character, self.sheet_b.character)
        self.assertEqual(result, 2)

    def test_returns_zero_when_no_progress_crosses_threshold(self) -> None:
        """Returns 0 when there is a relationship but points don't reach any tier."""
        track = RelationshipTrackFactory()
        RelationshipTierFactory(track=track, tier_number=1, point_threshold=50)
        rel = CharacterRelationshipFactory(
            source=self.sheet_a,
            target=self.sheet_b,
        )
        # Only 5 developed points — below the 50-point threshold
        RelationshipTrackProgressFactory(
            relationship=rel,
            track=track,
            capacity=10,
            developed_points=5,
        )
        result = get_relationship_tier(self.sheet_a.character, self.sheet_b.character)
        self.assertEqual(result, 0)
