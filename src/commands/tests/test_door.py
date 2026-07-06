"""Tests for the real CmdLock/CmdUnlock (#1866, replacing the stubs)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.types import ActionResult
from commands.door import CmdLock, CmdUnlock
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory


class CmdLockTests(TestCase):
    def _caller_and_exit(self):
        room = ObjectDBFactory(db_key="CmdLockRoom", db_typeclass_path="typeclasses.rooms.Room")
        destination = ObjectDBFactory(
            db_key="CmdLockDest", db_typeclass_path="typeclasses.rooms.Room"
        )
        account = AccountFactory(username="cmdlock_account")
        caller = CharacterFactory(db_key="CmdLockAlice", location=room)
        caller.db_account = account
        caller.save()
        exit_obj = ObjectDBFactory(db_key="gate", db_typeclass_path="typeclasses.exits.Exit")
        exit_obj.location = room
        exit_obj.destination = destination
        exit_obj.save()
        return caller, exit_obj

    def _run(
        self, cmd_cls, caller, args: str, *, kwargs_out: list[dict] | None = None
    ) -> list[str]:
        cmd = cmd_cls()
        cmd.caller = caller
        cmd.args = args
        cmd.raw_string = f"{cmd_cls.key} {args}"
        messages: list[str] = []

        def _msg(*a, **kw):
            if a:
                messages.append(a[0])
            if kw:
                if kwargs_out is not None:
                    kwargs_out.append(kw)

        cmd.msg = _msg
        cmd.func()
        return messages

    def test_lock_dispatches_lock_action(self):
        caller, exit_obj = self._caller_and_exit()
        with patch("commands.door.LockAction.run") as mocked:
            mocked.return_value = ActionResult(success=True, message="Locked.")
            self._run(CmdLock, caller, "gate")
        mocked.assert_called_once()
        assert mocked.call_args.kwargs["exit"] == exit_obj

    def test_unlock_dispatches_unlock_action(self):
        caller, exit_obj = self._caller_and_exit()
        with patch("commands.door.UnlockAction.run") as mocked:
            mocked.return_value = ActionResult(success=True, message="Unlocked.")
            self._run(CmdUnlock, caller, "gate")
        mocked.assert_called_once()
        assert mocked.call_args.kwargs["exit"] == exit_obj

    def test_lock_no_such_exit(self):
        caller, _ = self._caller_and_exit()
        kwargs_calls: list[dict] = []
        messages = self._run(CmdLock, caller, "nowhere", kwargs_out=kwargs_calls)
        assert any("find" in m.lower() or "such" in m.lower() for m in messages)

        assert len(kwargs_calls) == 1
        payload = kwargs_calls[0]["command_error"]
        assert "find" in payload["error"].lower() or "such" in payload["error"].lower()
        assert payload["command"] == "lock nowhere"
