"""Telnet E2E: comfort glance journey (#1514/#1522).

A light e2e test for ``CmdComfort`` — a read-only personal-comfort glance.
Proves the command wires up, runs without error against a real character in a
real room, and produces the expected output shape (personal band + room level).

This is not a state-changing journey; it's a smoke test that the read path
works end-to-end through the telnet command, not just the service layer.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase
from evennia.utils import idmapper

from commands.comfort import CmdComfort
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.vitals.factories import CharacterVitalsFactory


def _run(caller: object) -> CmdComfort:
    """Wire CmdComfort to *caller* and call func(). Returns the cmd instance."""
    cmd = CmdComfort()
    cmd.caller = caller
    cmd.args = ""
    cmd.raw_string = "comfort"
    cmd.cmdname = "comfort"
    caller.msg = MagicMock()
    cmd.func()
    return cmd


class ComfortTelnetE2EJourneyTest(TestCase):
    """Bare ``comfort`` → personal band + room level output."""

    def setUp(self) -> None:
        idmapper.models.flush_cache()
        self.room = ObjectDBFactory(
            db_key="ComfortE2ERoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.character = CharacterFactory(location=self.room)
        self.sheet = CharacterSheetFactory(character=self.character)
        # Full health so injury penalty is 0.
        CharacterVitalsFactory(character_sheet=self.sheet, health=100, max_health=100)

    def test_comfort_shows_personal_band_and_room_level(self) -> None:
        """``comfort`` → "You feel <band>." + room level line."""
        _run(self.character)

        self.character.msg.assert_called()
        msg = self.character.msg.call_args[0][0]

        # Personal band line.
        self.assertIn("you feel", msg.lower(), "should show personal comfort band")

        # Room level line.
        self.assertIn("room itself", msg.lower(), "should show the room's own comfort level")
        self.assertIn("/10", msg, "should show the room level out of 10")

    def test_comfort_without_location_gives_fallback(self) -> None:
        """``comfort`` with no location → fallback message."""
        self.character.location = None
        _run(self.character)

        self.character.msg.assert_called()
        msg = self.character.msg.call_args[0][0]
        self.assertIn("aren't anywhere", msg.lower())
