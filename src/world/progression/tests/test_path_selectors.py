"""Tests for progression path selectors (#954)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import PathFactory
from world.classes.models import PathStage
from world.progression.factories import CharacterPathHistoryFactory
from world.progression.selectors import current_path_for_character, next_path_options


class PathSelectorTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.prospect = PathFactory(name="Steel Prospect", stage=PathStage.PROSPECT)
        self.child_a = PathFactory(name="Steel Potential A", stage=PathStage.POTENTIAL)
        self.child_b = PathFactory(name="Steel Potential B", stage=PathStage.POTENTIAL)
        self.inactive_child = PathFactory(
            name="Steel Potential X", stage=PathStage.POTENTIAL, is_active=False
        )
        for child in (self.child_a, self.child_b, self.inactive_child):
            child.parent_paths.add(self.prospect)

    def test_current_path_none_without_history(self) -> None:
        assert current_path_for_character(self.character) is None

    def test_current_path_returns_latest_selection(self) -> None:
        CharacterPathHistoryFactory(character=self.sheet, path=self.prospect)
        assert current_path_for_character(self.character) == self.prospect

    def test_options_are_active_children(self) -> None:
        CharacterPathHistoryFactory(character=self.sheet, path=self.prospect)
        options = next_path_options(self.character)
        assert set(options) == {self.child_a, self.child_b}
        assert self.inactive_child not in options

    def test_options_empty_without_current_path(self) -> None:
        assert next_path_options(self.character) == []

    def test_options_empty_for_terminal_path(self) -> None:
        CharacterPathHistoryFactory(character=self.sheet, path=self.child_a)
        assert next_path_options(self.character) == []
