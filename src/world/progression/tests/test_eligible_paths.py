from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory, PathFactory
from world.classes.models import PathStage
from world.progression.models import CharacterPathHistory
from world.progression.selectors import eligible_advanced_paths_for, resolve_advanced_path_by_name


class EligiblePathTests(TestCase):
    def setUp(self) -> None:
        self.prospect = PathFactory(stage=PathStage.PROSPECT)
        self.potential = PathFactory(stage=PathStage.POTENTIAL, name="Ember Road")
        self.potential.parent_paths.add(self.prospect)
        self.sheet = CharacterSheetFactory()
        CharacterClassLevelFactory(
            character=self.sheet.character,
            character_class=CharacterClassFactory(),
            level=2,
            is_primary=True,
        )
        CharacterPathHistory.objects.create(character=self.sheet, path=self.prospect)

    def test_eligible_lists_potential_child(self) -> None:
        self.assertIn(self.potential, eligible_advanced_paths_for(self.sheet))

    def test_resolve_by_name_case_insensitive(self) -> None:
        self.assertEqual(resolve_advanced_path_by_name(self.sheet, "ember road"), self.potential)

    def test_resolve_unknown_returns_none(self) -> None:
        self.assertIsNone(resolve_advanced_path_by_name(self.sheet, "nope"))
