"""Door lock/unlock/pick/break telnet commands (#1866, #2176).

Real implementation replacing the former stubs — dispatches to
LockAction/UnlockAction/PickLockAction/BreakExitAction
(actions/definitions/doors.py). Room-owner/tenant gated (enforced by the
Action's prerequisite, not here) for lock/unlock; pick/break are the
intruder path gated only on having a character sheet.
"""

from __future__ import annotations

from typing import Any

from actions.definitions.doors import BreakExitAction, LockAction, PickLockAction, UnlockAction
from commands.command import ArxCommand


class CmdLock(ArxCommand):
    """Lock an exit in your current room.

    Usage:
      lock <exit name>
    """

    key = "lock"
    locks = "cmd:all()"
    action = LockAction()

    def resolve_action_args(self) -> dict[str, Any]:
        name = self.require_args("Lock which exit?")
        exit_obj = self.search_or_raise(
            name,
            location=self.caller.location,
            not_found_msg=f"Could not find an exit called '{name}'.",
        )
        return {"exit": exit_obj}


class CmdUnlock(ArxCommand):
    """Unlock an exit in your current room.

    Usage:
      unlock <exit name>
    """

    key = "unlock"
    locks = "cmd:all()"
    action = UnlockAction()

    def resolve_action_args(self) -> dict[str, Any]:
        name = self.require_args("Unlock which exit?")
        exit_obj = self.search_or_raise(
            name,
            location=self.caller.location,
            not_found_msg=f"Could not find an exit called '{name}'.",
        )
        return {"exit": exit_obj}


class CmdPick(ArxCommand):
    """Pick the lock on an exit in your current room.

    Usage:
      pick <exit name>
    """

    key = "pick"
    locks = "cmd:all()"
    action = PickLockAction()

    def resolve_action_args(self) -> dict[str, Any]:
        name = self.require_args("Pick which exit?")
        exit_obj = self.search_or_raise(
            name,
            location=self.caller.location,
            not_found_msg=f"Could not find an exit called '{name}'.",
        )
        return {"exit": exit_obj}


class CmdBreak(ArxCommand):
    """Break through the lock on an exit in your current room.

    Usage:
      break <exit name>
    """

    key = "break"
    locks = "cmd:all()"
    action = BreakExitAction()

    def resolve_action_args(self) -> dict[str, Any]:
        name = self.require_args("Break which exit?")
        exit_obj = self.search_or_raise(
            name,
            location=self.caller.location,
            not_found_msg=f"Could not find an exit called '{name}'.",
        )
        return {"exit": exit_obj}
