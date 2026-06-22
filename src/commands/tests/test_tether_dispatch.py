"""Smoke tests for CmdTether dispatch — verifies argument routing before the E2E."""

from unittest.mock import MagicMock

from django.test import TestCase

from commands.social.soul_tether import CmdTether


class TetherDispatchTests(TestCase):
    def _run(self, args):
        cmd = CmdTether()
        cmd.caller = MagicMock()
        cmd.caller.search.return_value = None
        cmd.args = args
        cmd.func()
        return cmd

    def test_unknown_subcommand_sends_usage(self):
        cmd = self._run("unknown")
        cmd.caller.msg.assert_called()
        assert "tether" in cmd.caller.msg.call_args[0][0].lower()

    def test_burden_search_miss_sends_error(self):
        cmd = self._run("burden Nobody resonance=Embers writeup=test")
        cmd.caller.msg.assert_called()
        msg = cmd.caller.msg.call_args[0][0]
        assert "Could not find" in msg or "could not find" in msg.lower()

    def test_burden_missing_resonance_sends_error(self):
        cmd = CmdTether()
        cmd.caller = MagicMock()
        target = MagicMock()
        target.sheet_data = MagicMock()
        cmd.caller.search.return_value = target
        cmd.args = "burden Bob writeup=test"
        cmd.func()
        msg = cmd.caller.msg.call_args[0][0]
        assert "resonance" in msg.lower()

    def test_burden_missing_writeup_sends_error(self):
        cmd = CmdTether()
        cmd.caller = MagicMock()
        target = MagicMock()
        target.sheet_data = MagicMock()
        cmd.caller.search.return_value = target
        cmd.args = "burden Bob resonance=Embers"
        cmd.func()
        msg = cmd.caller.msg.call_args[0][0]
        assert "writeup" in msg.lower()

    def test_dissolve_no_tether_sends_error(self):
        from evennia_extensions.factories import ObjectDBFactory
        from world.character_sheets.factories import CharacterSheetFactory

        room = ObjectDBFactory(db_key="DR", db_typeclass_path="typeclasses.rooms.Room")
        caller_char = ObjectDBFactory(
            db_key="DC", db_typeclass_path="typeclasses.characters.Character", location=room
        )
        _caller_sheet = CharacterSheetFactory(character=caller_char)
        target_char = ObjectDBFactory(
            db_key="DT", db_typeclass_path="typeclasses.characters.Character", location=room
        )
        _target_sheet = CharacterSheetFactory(character=target_char)

        cmd = CmdTether()
        cmd.caller = caller_char
        caller_char.msg = MagicMock()
        caller_char.search = MagicMock(return_value=target_char)
        cmd.args = f"dissolve {target_char.db_key}"
        cmd.func()
        caller_char.msg.assert_called()
        msg = caller_char.msg.call_args[0][0]
        assert "soul tether" in msg.lower()
