"""The telnet sheet's relationships section names a companion-targeted row (#3575)."""

from django.test import TestCase

from commands.account.sheet_sections import _format_relationships
from world.character_sheets.factories import CharacterSheetFactory
from world.companions.factories import CompanionFactory
from world.relationships.factories import CharacterRelationshipFactory


class FormatRelationshipsCompanionTests(TestCase):
    def test_companion_row_renders_the_companion_name(self) -> None:
        owner = CharacterSheetFactory()
        companion = CompanionFactory(owner=owner, name="Ash")
        rel = CharacterRelationshipFactory(
            source=owner, target=None, target_companion=companion, is_pending=False
        )
        rel.cached_track_progress = []
        rel.cached_updates = []
        lines = _format_relationships([rel])
        self.assertTrue(any("Ash" in line for line in lines), lines)
