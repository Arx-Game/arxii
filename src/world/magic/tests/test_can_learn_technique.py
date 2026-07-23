"""Tests for the can_learn_technique path-style gate (#1732)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import PathFactory
from world.magic.constants import GiftKind
from world.magic.factories import GiftFactory, TechniqueFactory, TechniqueStyleFactory
from world.magic.services.gift_acquisition import can_learn_technique
from world.progression.factories import CharacterPathHistoryFactory


class CanLearnTechniqueTest(TestCase):
    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.gift = GiftFactory(kind=GiftKind.MINOR)

    def test_blank_allowed_paths_allows_all(self):
        """Style with no allowed_paths = available to everyone."""
        style = TechniqueStyleFactory()  # no allowed_paths
        technique = TechniqueFactory(gift=self.gift, style=style)
        self.assertTrue(can_learn_technique(self.sheet, technique))

    def test_no_path_history_allows_all(self):
        """Character with no path history = no restriction."""
        path = PathFactory()
        style = TechniqueStyleFactory(allowed_paths=[path])
        technique = TechniqueFactory(gift=self.gift, style=style)
        self.assertTrue(can_learn_technique(self.sheet, technique))

    def test_matching_path_allows(self):
        """Character whose current path is in allowed_paths can learn."""
        path = PathFactory()
        CharacterPathHistoryFactory(character=self.sheet, path=path)
        style = TechniqueStyleFactory(allowed_paths=[path])
        technique = TechniqueFactory(gift=self.gift, style=style)
        self.assertTrue(can_learn_technique(self.sheet, technique))

    def test_non_matching_path_blocks(self):
        """Character whose current path is NOT in allowed_paths cannot learn."""
        allowed_path = PathFactory()
        other_path = PathFactory()
        CharacterPathHistoryFactory(character=self.sheet, path=other_path)
        style = TechniqueStyleFactory(allowed_paths=[allowed_path])
        technique = TechniqueFactory(gift=self.gift, style=style)
        self.assertFalse(can_learn_technique(self.sheet, technique))
