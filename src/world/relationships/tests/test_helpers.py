"""Tests for relationship helper functions (#3957: mutual Mentor/Student tier)."""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.relationships.constants import LabelAwareness, TypeFamily
from world.relationships.factories import CharacterRelationshipFactory, RelationshipTypeFactory
from world.relationships.helpers import get_relationship_tier
from world.relationships.services import declare_label
from world.roster.factories import grant_test_tenure


class GetRelationshipTierTests(TestCase):
    """Tests for get_relationship_tier."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        # bare ObjectDB characters with no CharacterSheet -- for no-sheet edge cases
        cls.char_a = CharacterFactory()
        cls.char_b = CharacterFactory()
        # Characters that have CharacterSheets (needed for relationship lookups)
        cls.sheet_a = CharacterSheetFactory()
        cls.sheet_b = CharacterSheetFactory()
        cls.tenure_a = grant_test_tenure(cls.sheet_a)
        cls.tenure_b = grant_test_tenure(cls.sheet_b)
        cls.mentor = RelationshipTypeFactory(name="Mentor", family=TypeFamily.TEACHING)
        cls.student = RelationshipTypeFactory(
            name="Student", family=TypeFamily.TEACHING, counterpart=cls.mentor
        )
        cls.mentor.counterpart = cls.student
        cls.mentor.save(update_fields=["counterpart"])

    def test_returns_zero_without_relationship(self) -> None:
        """Returns 0 when no relationship exists between the characters."""
        self.assertEqual(get_relationship_tier(self.sheet_a.character, self.sheet_b.character), 0)

    def test_returns_zero_when_character_has_no_sheet(self) -> None:
        """Returns 0 when a character has no CharacterSheet attached."""
        self.assertEqual(get_relationship_tier(self.char_a, self.char_b), 0)

    def test_mutual_mentor_student_returns_the_lower_claimed_tier(self) -> None:
        """A mutual Mentor/Student pair returns the lower of the two claimed tiers."""
        ab = CharacterRelationshipFactory(source=self.sheet_a, target=self.sheet_b, tier=2)
        ba = CharacterRelationshipFactory(source=self.sheet_b, target=self.sheet_a, tier=1)
        declare_label(
            side=ab, type=self.mentor, awareness=LabelAwareness.PUBLIC, tenure=self.tenure_a
        )
        declare_label(
            side=ba, type=self.student, awareness=LabelAwareness.PUBLIC, tenure=self.tenure_b
        )
        result = get_relationship_tier(self.sheet_a.character, self.sheet_b.character)
        self.assertEqual(result, 1)

    def test_one_sided_label_returns_zero(self) -> None:
        """Only one side naming the teaching label is not mutual -- returns 0."""
        ab = CharacterRelationshipFactory(source=self.sheet_a, target=self.sheet_b, tier=2)
        CharacterRelationshipFactory(source=self.sheet_b, target=self.sheet_a, tier=1)
        declare_label(
            side=ab, type=self.mentor, awareness=LabelAwareness.PUBLIC, tenure=self.tenure_a
        )
        result = get_relationship_tier(self.sheet_a.character, self.sheet_b.character)
        self.assertEqual(result, 0)
