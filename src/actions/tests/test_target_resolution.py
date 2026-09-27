"""The shared persona-pk resolver and Look's persona target (#4030)."""

from __future__ import annotations

import django.test

from actions.registry import get_action
from actions.target_resolution import resolve_persona_pk_to_character
from evennia_extensions.factories import RoomProfileFactory
from world.roster.factories import RosterEntryFactory
from world.scenes.services import create_mask


class ResolvePersonaPkTests(django.test.TestCase):
    def setUp(self) -> None:
        self.sheet = RosterEntryFactory().character_sheet
        self.character = self.sheet.character

    def test_primary_persona_resolves_to_its_character(self) -> None:
        assert resolve_persona_pk_to_character(self.sheet.primary_persona.pk) == self.character

    def test_mask_resolves_to_the_character_underneath(self) -> None:
        mask = create_mask(self.sheet, name="A Grey Hood")
        assert resolve_persona_pk_to_character(mask.pk) == self.character

    def test_unknown_or_malformed_pk_is_none(self) -> None:
        assert resolve_persona_pk_to_character(999_999) is None
        assert resolve_persona_pk_to_character("not-a-pk") is None
        assert resolve_persona_pk_to_character(None) is None


class LookAtPersonaTests(django.test.TestCase):
    def setUp(self) -> None:
        room = RoomProfileFactory().objectdb
        self.viewer = RosterEntryFactory().character_sheet.character
        self.viewer.move_to(room, quiet=True)
        target_sheet = RosterEntryFactory().character_sheet
        self.target = target_sheet.character
        self.target.move_to(room, quiet=True)
        self.persona = target_sheet.primary_persona

    def test_look_with_target_persona_id_describes_that_character(self) -> None:
        result = get_action("look").run(self.viewer, target_persona_id=self.persona.pk)
        assert result.success, result.message
        assert self.persona.name in result.message

    def test_look_with_unknown_persona_asks_what(self) -> None:
        result = get_action("look").run(self.viewer, target_persona_id=999_999)
        assert not result.success
        assert result.message == "Look at what?"
