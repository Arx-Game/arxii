"""ObjectParent.character_sheet — the safe, explicit sheet accessor (#1825 review).

Replaces the ``getattr(obj, "sheet_data", None)`` idiom: ``sheet_data`` is the reverse
OneToOne from ``CharacterSheet.character`` and RAISES on sheetless objects — the getattr
default only "worked" because Django's RelatedObjectDoesNotExist subclasses
AttributeError, which also silently swallowed genuine attribute bugs. ``character_sheet``
returns the sheet or None, and a typo'd attribute stays a loud AttributeError.
"""

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory


class CharacterSheetPropertyTests(TestCase):
    def test_character_with_sheet_returns_it(self):
        sheet = CharacterSheetFactory()
        assert sheet.character.character_sheet == sheet

    def test_sheetless_object_returns_none(self):
        room = RoomProfileFactory().objectdb
        assert room.character_sheet is None
