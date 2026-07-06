"""Door lock/unlock telnet commands (#1866).

Real implementation replacing the former stubs — dispatches to
LockAction/UnlockAction (actions/definitions/doors.py). Room-owner/tenant
gated (enforced by the Action's prerequisite, not here).
"""

from __future__ import annotations

from typing import Any

from actions.definitions.doors import LockAction, UnlockAction
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
