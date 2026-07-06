"""Door lock/unlock telnet commands (#1866).

Real implementation replacing the former stubs — dispatches to
LockAction/UnlockAction (actions/definitions/doors.py). Room-owner/tenant
gated (enforced by the Action's prerequisite, not here).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from actions.definitions.doors import LockAction, UnlockAction
from commands.command import ArxCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


class CmdLock(ArxCommand):
    """Lock an exit in your current room.

    Usage:
      lock <exit name>
    """

    key = "lock"
    locks = "cmd:all()"

    def func(self) -> None:
        try:
            exit_obj = self._resolve_exit()
        except CommandError as err:
            self.msg(str(err))
            return
        result = LockAction().run(actor=self.caller, exit=exit_obj)
        if result.message:
            self.msg(result.message)

    def _resolve_exit(self) -> ObjectDB:
        name = (self.args or "").strip()
        if not name:
            msg = "Lock which exit?"
            raise CommandError(msg)
        exit_obj = self.caller.search(name, location=self.caller.location)
        if not exit_obj:
            msg = f"Could not find an exit called '{name}'."
            raise CommandError(msg)
        return exit_obj


class CmdUnlock(ArxCommand):
    """Unlock an exit in your current room.

    Usage:
      unlock <exit name>
    """

    key = "unlock"
    locks = "cmd:all()"

    def func(self) -> None:
        try:
            exit_obj = self._resolve_exit()
        except CommandError as err:
            self.msg(str(err))
            return
        result = UnlockAction().run(actor=self.caller, exit=exit_obj)
        if result.message:
            self.msg(result.message)

    def _resolve_exit(self) -> ObjectDB:
        name = (self.args or "").strip()
        if not name:
            msg = "Unlock which exit?"
            raise CommandError(msg)
        exit_obj = self.caller.search(name, location=self.caller.location)
        if not exit_obj:
            msg = f"Could not find an exit called '{name}'."
            raise CommandError(msg)
        return exit_obj
