"""Gate 10.2 — spend_xp_on_unlock raises ProtagonismLockedError for subsumed sheets."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassLevelFactory
from world.magic.exceptions import ProtagonismLockedError
from world.magic.factories import ResonanceFactory, with_corruption_at_stage
from world.progression.services import spend_xp_on_unlock


class ProtagonismLockXPSpendTests(TestCase):
    """spend_xp_on_unlock is blocked for protagonism-locked characters."""

    def _make_subsumed_character(self):
        """Return an ObjectDB character whose sheet is at corruption stage 5."""
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        with_corruption_at_stage(sheet, resonance, stage=5)
        sheet.__dict__.pop("is_protagonism_locked", None)
        return sheet.character

    def test_subsumed_character_cannot_spend_xp(self) -> None:
        character = self._make_subsumed_character()
        unlock = CharacterClassLevelFactory()

        with self.assertRaises(ProtagonismLockedError):
            spend_xp_on_unlock(character, unlock)
