"""Tests for cross-path style comparison (#2711)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import PathFactory
from world.magic.factories import TechniqueStyleFactory
from world.magic.services.technique_progress import is_cross_path_learning
from world.progression.factories import CharacterPathHistoryFactory
from world.roster.factories import RosterTenureFactory


class CrossPathStyleTest(TestCase):
    def setUp(self):
        self.style_a = TechniqueStyleFactory()
        self.style_b = TechniqueStyleFactory()
        self.path_a = PathFactory(style=self.style_a)
        self.path_b = PathFactory(style=self.style_b)
        self.path_null = PathFactory(style=None)

    def _make_teacher(self, path):
        teacher = RosterTenureFactory()
        sheet = teacher.roster_entry.character_sheet
        CharacterPathHistoryFactory(character=sheet, path=path)
        return teacher

    def test_same_style_not_cross_path(self):
        learner = CharacterSheetFactory()
        CharacterPathHistoryFactory(character=learner, path=self.path_a)
        teacher = self._make_teacher(self.path_a)
        self.assertFalse(is_cross_path_learning(teacher, learner))

    def test_different_styles_cross_path(self):
        learner = CharacterSheetFactory()
        CharacterPathHistoryFactory(character=learner, path=self.path_a)
        teacher = self._make_teacher(self.path_b)
        self.assertTrue(is_cross_path_learning(teacher, learner))

    def test_null_teacher_style_fail_open(self):
        learner = CharacterSheetFactory()
        CharacterPathHistoryFactory(character=learner, path=self.path_a)
        teacher = self._make_teacher(self.path_null)
        self.assertFalse(is_cross_path_learning(teacher, learner))

    def test_null_learner_style_fail_open(self):
        learner = CharacterSheetFactory()
        CharacterPathHistoryFactory(character=learner, path=self.path_null)
        teacher = self._make_teacher(self.path_a)
        self.assertFalse(is_cross_path_learning(teacher, learner))

    def test_no_teacher_tenure_not_cross_path(self):
        learner = CharacterSheetFactory()
        CharacterPathHistoryFactory(character=learner, path=self.path_a)
        self.assertFalse(is_cross_path_learning(None, learner))

    def test_no_path_history_fail_open(self):
        """Characters with no path history at all → not cross-path."""
        learner = CharacterSheetFactory()
        teacher = RosterTenureFactory()
        self.assertFalse(is_cross_path_learning(teacher, learner))
