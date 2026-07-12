"""NPC guard assignment actions (#2178).

Owner-gated actions to assign/unassign NPCs as guards and view current
assignments. Shared by telnet (``CmdGuard``) and the web dispatcher.
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
class AssignGuardAction(Action):
    """Assign a Functionary or NPCAsset as a guard to the actor's room.

    Kwargs:
        source_type: ``"functionary"`` or ``"npc_asset"``.
        npc_id: The pk of the Functionary or NPCAsset.
        room_id: Optional web canvas anchor (defaults to actor.location).
    """

    key: str = "assign_guard"
    name: str = "Assign Guard"
    icon: str = "shield"
    category: str = "npc_services"
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
        from django.utils import timezone  # noqa: PLC0415

        from world.npc_services.models import (  # noqa: PLC0415
            AssignmentRole,
            NPCAssignment,
            NPCSourceType,
        )
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        room = _resolve_room(actor, kwargs)
        if room is None:
            return ActionResult(success=False, message=_no_room_message(kwargs))

        source_type = kwargs.get("source_type", "")
        npc_id = kwargs.get("npc_id")

        if source_type == NPCSourceType.FUNCTIONARY.value:
            from world.npc_services.models import Functionary  # noqa: PLC0415

            npc = Functionary.objects.filter(pk=npc_id).first()
            if npc is None:
                return ActionResult(success=False, message="No such functionary.")
            source_type_enum = NPCSourceType.FUNCTIONARY
        elif source_type == NPCSourceType.NPC_ASSET.value:
            from world.assets.models import NPCAsset  # noqa: PLC0415

            npc = NPCAsset.objects.filter(pk=npc_id).first()
            if npc is None:
                return ActionResult(success=False, message="No such NPC asset.")
            source_type_enum = NPCSourceType.NPC_ASSET
        else:
            return ActionResult(success=False, message="Invalid source type.")

        profile = _room_profile_for(room)
        if profile is None:
            return ActionResult(success=False, message="This room has no profile.")

        persona = active_persona_for_sheet(actor.sheet_data)

        # Retire any existing active guard for this room.
        NPCAssignment.objects.filter(
            room=profile,
            assignment_role=AssignmentRole.GUARD,
            is_active=True,
        ).update(is_active=False, ended_at=timezone.now())

        assignment = NPCAssignment.objects.create(
            source_type=source_type_enum,
            functionary=npc if source_type_enum == NPCSourceType.FUNCTIONARY else None,
            npc_asset=npc if source_type_enum == NPCSourceType.NPC_ASSET else None,
            room=profile,
            assignment_role=AssignmentRole.GUARD,
            assigned_by=persona,
        )
        return ActionResult(
            success=True,
            message=f"{assignment.get_active_target_name()} is now on guard duty.",
        )


@dataclass
class UnassignGuardAction(Action):
    """Retire the active guard assignment in the actor's room.

    Kwargs:
        room_id: Optional web canvas anchor (defaults to actor.location).
    """

    key: str = "unassign_guard"
    name: str = "Unassign Guard"
    icon: str = "shield-off"
    category: str = "npc_services"
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
        from django.utils import timezone  # noqa: PLC0415

        from world.npc_services.models import (  # noqa: PLC0415
            AssignmentRole,
            NPCAssignment,
        )

        room = _resolve_room(actor, kwargs)
        if room is None:
            return ActionResult(success=False, message=_no_room_message(kwargs))

        profile = _room_profile_for(room)
        if profile is None:
            return ActionResult(success=False, message="This room has no profile.")

        updated = NPCAssignment.objects.filter(
            room=profile,
            assignment_role=AssignmentRole.GUARD,
            is_active=True,
        ).update(is_active=False, ended_at=timezone.now())

        if updated == 0:
            return ActionResult(success=False, message="There is no guard assigned here.")
        return ActionResult(success=True, message="Guard unassigned.")


@dataclass
class ListGuardAssignmentsAction(Action):
    """List active guard assignments in the actor's room.

    Kwargs:
        room_id: Optional web canvas anchor (defaults to actor.location).
    """

    key: str = "list_guard_assignments"
    name: str = "Guard Assignments"
    icon: str = "list"
    category: str = "npc_services"
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
        from world.npc_services.models import (  # noqa: PLC0415
            AssignmentRole,
            NPCAssignment,
        )

        room = _resolve_room(actor, kwargs)
        if room is None:
            return ActionResult(success=False, message=_no_room_message(kwargs))

        profile = _room_profile_for(room)
        if profile is None:
            return ActionResult(
                success=True, message="No guard assignments.", data={"assignments": []}
            )

        assignments = NPCAssignment.objects.filter(
            room=profile,
            assignment_role=AssignmentRole.GUARD,
            is_active=True,
        ).select_related("functionary", "npc_asset")

        if not assignments:
            return ActionResult(
                success=True, message="No guard assignments.", data={"assignments": []}
            )

        data = [
            {
                "id": a.pk,
                "name": a.get_active_target_name(),
                "role": a.assignment_role,
                "source_type": a.source_type,
            }
            for a in assignments
        ]
        return ActionResult(
            success=True,
            message=f"{len(data)} guard(s) assigned.",
            data={"assignments": data},
        )


def _resolve_room(actor: ObjectDB, kwargs: dict[str, Any]) -> ObjectDB | None:
    """Resolve the anchor room: explicit room_id (web) else actor.location."""
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415

    room_id = kwargs.get("room_id")
    if room_id:
        profile = RoomProfile.objects.filter(objectdb_id=room_id).select_related("objectdb").first()
        return profile.objectdb if profile else None
    return actor.location


def _room_profile_for(room: ObjectDB):
    """Resolve the RoomProfile for a room ObjectDB."""
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415

    return RoomProfile.objects.filter(objectdb=room).first()


def _no_room_message(kwargs: dict[str, Any]) -> str:
    return "No such room." if kwargs.get("room_id") else "You're not in a room."
