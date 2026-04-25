"""Tests for CharacterSheet.current_residence FK (Spec C)."""

from django.test import TestCase


class CharacterSheetResidenceTests(TestCase):
    def test_current_residence_default_none(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory

        sheet = CharacterSheetFactory()
        self.assertIsNone(sheet.current_residence)

    def test_set_residence_fk(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.character_sheets.factories import CharacterSheetFactory

        sheet = CharacterSheetFactory()
        rp = RoomProfileFactory()
        sheet.current_residence = rp
        sheet.save(update_fields=["current_residence"])
        sheet.refresh_from_db()
        self.assertEqual(sheet.current_residence, rp)
