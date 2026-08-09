"""Tests for CmdDisarm — telnet face of DisarmTrapAction (#3011)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.types import ActionResult
from commands.exceptions import CommandError
from commands.traps import CmdDisarm
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.room_features.factories import TrapFactory


def _make_cmd(caller, args: str) -> CmdDisarm:
    cmd = CmdDisarm()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"disarm {args}".strip()
    return cmd


class CmdDisarmTests(TestCase):
    def setUp(self) -> None:
        self.room = ObjectDBFactory(
            db_key="CmdDisarmRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.caller = CharacterFactory(db_key="CmdDisarmBob", location=self.room)
        self.sheet = CharacterSheetFactory(character=self.caller)

        self.messages: list[str] = []
        self.caller.msg = lambda *a, **kw: self.messages.append(a[0] if a else "")  # noqa: ARG005

    def _run(self, args: str) -> None:
        cmd = _make_cmd(self.caller, args)
        cmd.func()

    def test_disarm_dispatches_the_resolved_trap_id(self) -> None:
        trap = TrapFactory(room_profile__objectdb=self.room, name="Obvious Snare", is_hidden=False)

        with patch.object(
            CmdDisarm.action.__class__,
            "run",
            return_value=ActionResult(success=True, message="You disarm Obvious Snare."),
        ) as mocked:
            self._run("Obvious Snare")

        mocked.assert_called_once()
        kwargs = mocked.call_args.kwargs
        assert kwargs["trap_id"] == trap.pk
        assert self.messages == ["You disarm Obvious Snare."]

    def test_disarm_is_case_insensitive(self) -> None:
        trap = TrapFactory(room_profile__objectdb=self.room, name="Obvious Snare", is_hidden=False)

        with patch.object(
            CmdDisarm.action.__class__,
            "run",
            return_value=ActionResult(success=True, message="ok"),
        ) as mocked:
            self._run("obvious snare")

        mocked.assert_called_once()
        assert mocked.call_args.kwargs["trap_id"] == trap.pk

    def test_disarm_unknown_name_raises_command_error_and_dispatches_nothing(self) -> None:
        with patch.object(CmdDisarm.action.__class__, "run") as mocked:
            self._run("Nonexistent Trap")

        mocked.assert_not_called()
        assert any("no such trap" in m.lower() for m in self.messages)

    def test_disarm_hidden_undetected_trap_is_not_resolvable_by_name(self) -> None:
        """The command's visibility rule mirrors ``RoomTrapViewSet``'s leak table:
        a hidden trap this caller hasn't detected can't be named."""
        TrapFactory(room_profile__objectdb=self.room, name="Hidden Pit", is_hidden=True)

        with patch.object(CmdDisarm.action.__class__, "run") as mocked:
            self._run("Hidden Pit")

        mocked.assert_not_called()
        assert any("no such trap" in m.lower() for m in self.messages)

    def test_disarm_hidden_trap_resolvable_once_this_caller_detected_it(self) -> None:
        trap = TrapFactory(room_profile__objectdb=self.room, name="Hidden Pit", is_hidden=True)
        trap.detected_by.add(self.sheet)

        with patch.object(
            CmdDisarm.action.__class__,
            "run",
            return_value=ActionResult(success=True, message="ok"),
        ) as mocked:
            self._run("Hidden Pit")

        mocked.assert_called_once()
        assert mocked.call_args.kwargs["trap_id"] == trap.pk

    def test_disarm_with_no_args_raises_command_error(self) -> None:
        cmd = _make_cmd(self.caller, "")
        with self.assertRaises(CommandError):
            cmd.resolve_action_args()


class CmdDisarmCmdsetRegistrationTests(TestCase):
    def test_disarm_command_registered(self) -> None:
        from commands.default_cmdsets import CharacterCmdSet

        cmdset = CharacterCmdSet()
        cmdset.at_cmdset_creation()
        keys = {c.key for c in cmdset.commands}
        self.assertIn("disarm", keys)
