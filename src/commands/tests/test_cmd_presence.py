"""Tests for the presence-privacy toggles (#1463): ``afk`` and ``hide``/``unhide``."""

from unittest.mock import MagicMock

from django.test import TestCase

from commands.presence import CMD_UNHIDE, CmdAfk, CmdHide
from evennia_extensions.factories import CharacterFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.roster.models import TenureDisplaySettings


class CmdAfkTests(TestCase):
    def test_afk_toggles_the_transient_marker(self) -> None:
        char = CharacterFactory(db_key="Caia")
        char.msg = MagicMock()

        cmd = CmdAfk()
        cmd.caller = char
        cmd.args = ""
        cmd.func()
        assert char.ndb.appear_afk is True

        again = CmdAfk()
        again.caller = char
        again.args = ""
        again.func()
        assert char.ndb.appear_afk is False


class CmdHideTests(TestCase):
    def setUp(self) -> None:
        self.char = CharacterFactory(db_key="Caia")
        self.char.msg = MagicMock()
        entry = RosterEntryFactory(character_sheet__character=self.char)
        self.tenure = RosterTenureFactory(roster_entry=entry)

    def _run(self, verb: str) -> None:
        cmd = CmdHide()
        cmd.caller = self.char
        cmd.cmdstring = verb
        cmd.args = ""
        cmd.func()

    def _appear_offline(self) -> bool:
        return TenureDisplaySettings.objects.get(tenure=self.tenure).appear_offline

    def test_hide_sets_and_unhide_clears_persistently(self) -> None:
        self._run(CmdHide.key)
        assert self._appear_offline() is True  # row created + set
        self._run(CmdHide.key)
        assert self._appear_offline() is False  # toggles back off
        self._run(CmdHide.key)
        assert self._appear_offline() is True
        self._run(CMD_UNHIDE)
        assert self._appear_offline() is False  # unhide always clears

    def test_non_rostered_caller_is_told_only_rostered_can_hide(self) -> None:
        bare = CharacterFactory(db_key="Drifter")
        bare.msg = MagicMock()
        cmd = CmdHide()
        cmd.caller = bare
        cmd.cmdstring = CmdHide.key
        cmd.args = ""
        cmd.func()
        bare.msg.assert_called_once()
        assert "rostered" in bare.msg.call_args[0][0].lower()
