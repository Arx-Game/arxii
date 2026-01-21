"""Tests for PathSkillSuggestion with Path model."""

from django.test import TestCase

from world.classes.factories import PathFactory
from world.classes.models import PathStage
from world.skills.factories import SkillFactory
from world.skills.models import PathSkillSuggestion


class PathSkillSuggestionPathTest(TestCase):
    """Tests for PathSkillSuggestion referencing Path."""

    @classmethod
    def setUpTestData(cls):
        cls.path = PathFactory(name="Path of Steel", stage=PathStage.PROSPECT)
        cls.melee = SkillFactory()
        cls.defense = SkillFactory()

    def test_create_suggestion_with_path(self):
        """Can create skill suggestion linked to Path."""
        suggestion = PathSkillSuggestion.objects.create(
            character_path=self.path,
            skill=self.melee,
            suggested_value=20,
        )
        self.assertEqual(suggestion.character_path, self.path)
        self.assertEqual(suggestion.skill, self.melee)
        self.assertEqual(suggestion.suggested_value, 20)

    def test_path_skill_suggestions_relationship(self):
        """Can access suggestions through path."""
        PathSkillSuggestion.objects.create(
            character_path=self.path, skill=self.melee, suggested_value=20
        )
        PathSkillSuggestion.objects.create(
            character_path=self.path, skill=self.defense, suggested_value=20
        )

        self.assertEqual(self.path.skill_suggestions.count(), 2)
