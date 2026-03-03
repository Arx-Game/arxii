"""Exit command that delegates to TraverseExitAction."""

from __future__ import annotations

from typing import Any

from actions.definitions.movement import TraverseExitAction
from commands.command import ArxCommand


class CmdExit(ArxCommand):
    """Traverse an exit.

    This command is dynamically created for each exit and allows characters
    to traverse exits using the action system.
    """

    action = TraverseExitAction()

    def resolve_action_args(self) -> dict[str, Any]:
        """Provide the exit object as the target."""
        if not self.obj:
            return {}
        return {"target": self.obj}
