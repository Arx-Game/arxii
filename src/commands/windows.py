"""Open/close window telnet commands (#2175).

Thin wrappers over OpenWindowAction/CloseWindowAction, mirroring the
#1866 door lock/unlock command pattern.
"""

from __future__ import annotations

from typing import Any

from actions.definitions.windows import CloseWindowAction, OpenWindowAction
from commands.command import ArxCommand


class CmdOpenWindow(ArxCommand):
    """Open a window exit in your current room.

    Usage:
      open <exit name>
    """

    key = "open"
    locks = "cmd:all()"
    action = OpenWindowAction()

    def resolve_action_args(self) -> dict[str, Any]:
        name = self.require_args("Open which exit?")
        exit_obj = self.search_or_raise(
            name,
            location=self.caller.location,
            not_found_msg=f"Could not find an exit called '{name}'.",
        )
        return {"exit": exit_obj}


class CmdCloseWindow(ArxCommand):
    """Close a window exit in your current room.

    Usage:
      close <exit name>
    """

    key = "close"
    locks = "cmd:all()"
    action = CloseWindowAction()

    def resolve_action_args(self) -> dict[str, Any]:
        name = self.require_args("Close which exit?")
        exit_obj = self.search_or_raise(
            name,
            location=self.caller.location,
            not_found_msg=f"Could not find an exit called '{name}'.",
        )
        return {"exit": exit_obj}
