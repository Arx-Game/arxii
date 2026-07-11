"""Tests for CmdOpenWindow / CmdCloseWindow (#2175)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.types import ActionResult
from commands.windows import CmdCloseWindow, CmdOpenWindow
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory


class CmdWindowTests(TestCase):
    def _caller_and_exit(self):
        room = ObjectDBFactory(db_key="CmdWinRoom", db_typeclass_path="typeclasses.rooms.Room")
        destination = ObjectDBFactory(
            db_key="CmdWinDest", db_typeclass_path="typeclasses.rooms.Room"
        )
        account = AccountFactory(username="cmdwin_account")
        caller = CharacterFactory(db_key="CmdWinCaller", location=room)
        caller.db_account = account
        caller.save()
        exit_obj = ObjectDBFactory(db_key="window", db_typeclass_path="typeclasses.exits.Exit")
        exit_obj.location = room
        exit_obj.destination = destination
        exit_obj.save()
        return caller, exit_obj

    def _run(self, cmd_cls, caller, args: str) -> list[str]:
        cmd = cmd_cls()
        cmd.caller = caller
        cmd.args = args
        cmd.raw_string = f"{cmd_cls.key} {args}"
        messages: list[str] = []

        def _msg(*a, **kw):
            if a:
                messages.append(a[0])

        cmd.msg = _msg
        cmd.func()
        return messages

    def test_open_dispatches_action(self):
        caller, exit_obj = self._caller_and_exit()
        with patch("commands.windows.OpenWindowAction.run") as mocked:
            mocked.return_value = ActionResult(success=True, message="You open window.")
            self._run(CmdOpenWindow, caller, "window")
        mocked.assert_called_once()
        assert mocked.call_args.kwargs["exit"] == exit_obj

    def test_close_dispatches_action(self):
        caller, exit_obj = self._caller_and_exit()
        with patch("commands.windows.CloseWindowAction.run") as mocked:
            mocked.return_value = ActionResult(success=True, message="You close window.")
            self._run(CmdCloseWindow, caller, "window")
        mocked.assert_called_once()
        assert mocked.call_args.kwargs["exit"] == exit_obj
