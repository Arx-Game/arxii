"""Open/close window actions (#2175).

Owner/tenant-gated, mirroring the #1866 door-lock pattern. Uses
``IsExitRoomOwnerPrerequisite`` which checks owner OR tenant standing
on the exit's source room.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.prerequisites import IsExitRoomOwnerPrerequisite, Prerequisite
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext


@dataclass
class OpenWindowAction(Action):
    """Open a window exit, allowing traversal and lowering room enclosure."""

    key: str = "open_window"
    name: str = "Open Window"
    icon: str = "square-arrow-out-up-right"
    category: str = "locations"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IsExitRoomOwnerPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from evennia_extensions.services.exits import is_window, set_window_open  # noqa: PLC0415

        exit_obj = kwargs.get("exit")
        if exit_obj is None:
            return ActionResult(success=False, message="Open which exit?")
        if not is_window(exit_obj):
            return ActionResult(success=False, message="That is not a window.")
        set_window_open(exit_obj, True)
        return ActionResult(success=True, message=f"You open {exit_obj.key}.")


@dataclass
class CloseWindowAction(Action):
    """Close a window exit, blocking traversal and restoring room enclosure."""

    key: str = "close_window"
    name: str = "Close Window"
    icon: str = "square"
    category: str = "locations"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IsExitRoomOwnerPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from evennia_extensions.services.exits import is_window, set_window_open  # noqa: PLC0415

        exit_obj = kwargs.get("exit")
        if exit_obj is None:
            return ActionResult(success=False, message="Close which exit?")
        if not is_window(exit_obj):
            return ActionResult(success=False, message="That is not a window.")
        set_window_open(exit_obj, False)
        return ActionResult(success=True, message=f"You close {exit_obj.key}.")
