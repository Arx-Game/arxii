"""Player-facing room editing actions (#1470) — the room-editor MVP seam.

``RoomEditAction`` lets a room **owner** edit the room they're standing in: its
display name, description, and public/private listing. It is the single seam both
telnet (``CmdManageRoom``) and the web (action-dispatch + ``RoomEditorPanel``)
call. Ownership is gated by ``IsRoomOwnerPrerequisite``; the write + the
public-toggle guard live in ``world.locations.services.set_room_display_data``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from evennia.objects.models import ObjectDB

from actions.base import Action
from actions.constants import ActionCategory
from actions.prerequisites import IsRoomOwnerPrerequisite, Prerequisite
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from actions.types import ActionContext


@dataclass
class RoomEditAction(Action):
    """Owner edits the room they're standing in: name, description, public/private.

    Operates on ``actor.location`` (the room the actor is in). Each field is
    optional — only those supplied are changed.
    """

    key: str = "edit_room"
    name: str = "Edit Room"
    icon: str = "home"
    category: str = "locations"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IsRoomOwnerPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.locations.services import (  # noqa: PLC0415
            RoomEditError,
            set_room_display_data,
        )
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        room = actor.location
        if room is None:
            return ActionResult(success=False, message="You're not in a room.")
        persona = active_persona_for_sheet(actor.sheet_data)
        try:
            set_room_display_data(
                room=room,
                persona=persona,
                name=kwargs.get("name"),
                description=kwargs.get("description"),
                is_public=kwargs.get("is_public"),
            )
        except RoomEditError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message="Room updated.")
