"""Door lock/unlock Actions (#1866).

Lock state is a plain Evennia attribute on the Exit object (``db.locked``)
— no new Django model, no migration. Room-owner/tenant gated, not
key-item gated (user decision, spec #1866): the simplest option reusing the
existing room-ownership substrate.
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
class LockAction(Action):
    """Lock an exit, blocking traversal for anyone but the room's owner/tenant."""

    key: str = "lock_exit"
    name: str = "Lock Exit"
    icon: str = "lock"
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
        exit_obj = kwargs.get("exit")
        if exit_obj is None:
            return ActionResult(success=False, message="Lock which exit?")
        exit_obj.db.locked = True
        return ActionResult(success=True, message=f"You lock {exit_obj.key}.")


@dataclass
class UnlockAction(Action):
    """Unlock an exit."""

    key: str = "unlock_exit"
    name: str = "Unlock Exit"
    icon: str = "lock-open"
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
        exit_obj = kwargs.get("exit")
        if exit_obj is None:
            return ActionResult(success=False, message="Unlock which exit?")
        exit_obj.db.locked = False
        return ActionResult(success=True, message=f"You unlock {exit_obj.key}.")
