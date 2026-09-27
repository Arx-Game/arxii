"""Room examine names a HELD captive by their presented face, never their real
key, for a non-staff observer (#4030)."""

from __future__ import annotations

import django.test

from actions.registry import get_action
from evennia_extensions.factories import AccountFactory
from world.captivity.services import capture_character
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterEntryFactory
from world.scenes.services import create_mask

MASK_NAME = "iron hood"


class CaptivityStatusPresentedNameTests(django.test.TestCase):
    def setUp(self) -> None:
        observer_entry = RosterEntryFactory()
        self.observer = observer_entry.character_sheet.character
        self.observer.db_account = AccountFactory(is_staff=False)
        self.observer.save()

        self.captive_sheet = CharacterSheetFactory()
        self.captive = self.captive_sheet.character
        captivity = capture_character(captive=self.captive_sheet)
        self.room = captivity.cell.room.objectdb
        self.observer.move_to(self.room, quiet=True)

        create_mask(self.captive_sheet, name=MASK_NAME)

    def test_masked_captive_named_by_presented_face_not_real_key(self) -> None:
        message = get_action("look").run(self.observer, target=self.room).message
        assert MASK_NAME in message
        assert self.captive.key not in message
